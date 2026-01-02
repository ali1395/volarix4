"""Grid search for parameter optimization using walk-forward validation.

Performs exhaustive grid search over parameter combinations, evaluating each
using walk-forward testing and selecting the best based on specified objective.
"""

from typing import List, Dict, Optional, Any
from itertools import product
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import logging
import json
import pandas as pd
import copy

from .config import BacktestConfig
from .data_source import BarDataSource
from .api_client import SignalApiClient
from .broker_sim import BrokerSimulator
from .walk_forward import WalkForwardEngine


class GridSearchEngine:
    """Grid search engine for parameter optimization.

    Runs walk-forward testing for each parameter combination in parallel
    and selects the best based on specified objective metric.
    """

    def __init__(
        self,
        config: BacktestConfig,
        data_source: BarDataSource,
        api_client: SignalApiClient,
        broker: BrokerSimulator,
        logger: Optional[logging.Logger] = None
    ):
        """Initialize grid search engine.

        Args:
            config: Backtest configuration with grid parameters
            data_source: Data source for loading bars
            api_client: API client for signals
            broker: Broker simulator
            logger: Optional logger
        """
        self.config = config
        self.data_source = data_source
        self.api_client = api_client
        self.broker = broker
        self.logger = logger or logging.getLogger(__name__)

        if not config.is_grid_search():
            raise ValueError("GridSearchEngine requires mode='grid_search' and grid parameters in config")

    def run(self) -> Dict:
        """Run grid search across all parameter combinations.

        Returns:
            Dictionary with results, best params, and output file paths
        """
        self.logger.info("=" * 70)
        self.logger.info("GRID SEARCH OPTIMIZATION")
        self.logger.info("=" * 70)
        self.logger.info(f"Objective: {self.config.objective}")
        self.logger.info(f"Parallel workers: {self.config.n_jobs}")
        self.logger.info(f"Grid parameters:")
        for param, values in self.config.grid.items():
            self.logger.info(f"  {param}: {values}")
        self.logger.info("=" * 70)

        # Generate all parameter combinations
        combinations = self._generate_combinations()
        total_combos = len(combinations)
        self.logger.info(f"Total combinations to test: {total_combos}")

        # Run grid search (parallel or sequential)
        if self.config.n_jobs == 1:
            results = self._run_sequential(combinations)
        else:
            results = self._run_parallel(combinations)

        # Sort results by objective
        results = self._sort_results(results)

        # Get best parameters
        best_result = results[0] if results else None

        # Generate output files
        output_files = self._generate_outputs(results, best_result)

        self.logger.info("=" * 70)
        self.logger.info("GRID SEARCH COMPLETE")
        self.logger.info("=" * 70)

        if best_result:
            self._print_best_results(results[:5])  # Top 5

        return {
            "results": results,
            "best_result": best_result,
            "total_combinations": total_combos,
            "output_files": output_files
        }

    def _generate_combinations(self) -> List[Dict[str, Any]]:
        """Generate all parameter combinations from grid.

        Returns:
            List of parameter dictionaries
        """
        # Get parameter names and values
        param_names = list(self.config.grid.keys())
        param_values = [self.config.grid[name] for name in param_names]

        # Generate all combinations
        combinations = []
        for combo in product(*param_values):
            param_dict = dict(zip(param_names, combo))
            combinations.append(param_dict)

        return combinations

    def _run_sequential(self, combinations: List[Dict]) -> List[Dict]:
        """Run grid search sequentially.

        Args:
            combinations: List of parameter combinations

        Returns:
            List of result dictionaries
        """
        results = []
        total = len(combinations)

        for i, params in enumerate(combinations, 1):
            self.logger.info(f"\n[{i}/{total}] Testing combination: {params}")

            result = self._evaluate_combination(params, i, total)

            if result:
                results.append(result)
                self.logger.info(
                    f"  → {self.config.objective} = {result['metrics'].get(self.config.objective, 'N/A'):.4f}"
                )
            else:
                self.logger.warning(f"  → Failed")

        return results

    def _run_parallel(self, combinations: List[Dict]) -> List[Dict]:
        """Run grid search in parallel using process pool.

        Args:
            combinations: List of parameter combinations

        Returns:
            List of result dictionaries
        """
        results = []
        total = len(combinations)
        completed = 0

        # Determine number of workers
        n_jobs = self.config.n_jobs
        if n_jobs == -1:
            import os
            n_jobs = os.cpu_count()

        self.logger.info(f"Running with {n_jobs} parallel workers")

        # Create process pool
        with ProcessPoolExecutor(max_workers=n_jobs) as executor:
            # Submit all tasks
            futures = {}
            for i, params in enumerate(combinations, 1):
                future = executor.submit(
                    _evaluate_combination_worker,
                    self.config,
                    params,
                    i,
                    total
                )
                futures[future] = (i, params)

            # Collect results as they complete
            for future in as_completed(futures):
                i, params = futures[future]
                completed += 1

                try:
                    result = future.result()
                    if result:
                        results.append(result)
                        self.logger.info(
                            f"[{completed}/{total}] Completed {params} → "
                            f"{self.config.objective} = {result['metrics'].get(self.config.objective, 'N/A'):.4f}"
                        )
                    else:
                        self.logger.warning(f"[{completed}/{total}] Failed {params}")
                except Exception as e:
                    self.logger.error(f"[{completed}/{total}] Error {params}: {e}")

        return results

    def _evaluate_combination(self, params: Dict, index: int, total: int) -> Optional[Dict]:
        """Evaluate a single parameter combination using walk-forward.

        Args:
            params: Parameter dictionary
            index: Combination index
            total: Total combinations

        Returns:
            Result dictionary or None if failed
        """
        try:
            # Create config with overridden parameters
            config = self._merge_config(params)

            # Create fresh data source for this combination
            data_source = BarDataSource(
                source=config.source,
                symbol=config.symbol,
                timeframe=config.timeframe,
                start_date=config.start_date,
                end_date=config.end_date,
                bars=config.bars,
                file_path=config.file_path
            )

            # Create fresh API client and broker
            pip_value = 0.0001 if "JPY" not in config.symbol else 0.01

            api_client = SignalApiClient(
                base_url=config.api_url,
                timeout=config.api_timeout,
                max_retries=config.api_max_retries,
                logger=self.logger
            )

            broker = BrokerSimulator(
                spread_pips=config.spread_pips,
                slippage_pips=config.slippage_pips,
                commission_per_side_per_lot=config.commission_per_side_per_lot,
                usd_per_pip_per_lot=config.usd_per_pip_per_lot,
                pip_value=pip_value
            )

            # Run walk-forward
            engine = WalkForwardEngine(config, data_source, api_client, broker, self.logger)
            wf_results = engine.run()

            # Extract aggregate metrics
            metrics = wf_results["aggregate"]

            # Close connections
            api_client.close()

            return {
                "params": params,
                "metrics": metrics,
                "by_year": wf_results["by_year"]
            }

        except Exception as e:
            self.logger.error(f"Error evaluating {params}: {e}")
            return None

    def _merge_config(self, params: Dict) -> BacktestConfig:
        """Merge grid parameters into base config.

        Args:
            params: Parameter dictionary

        Returns:
            New BacktestConfig with merged parameters
        """
        # Create a copy of the base config
        config_dict = copy.deepcopy(self.config.__dict__)

        # Override with grid parameters
        for key, value in params.items():
            config_dict[key] = value

        # Create new config instance
        return BacktestConfig(**config_dict)

    def _sort_results(self, results: List[Dict]) -> List[Dict]:
        """Sort results by objective metric (descending).

        Args:
            results: List of result dictionaries

        Returns:
            Sorted list
        """
        objective = self.config.objective

        def get_objective_value(result):
            return result["metrics"].get(objective, float('-inf'))

        return sorted(results, key=get_objective_value, reverse=True)

    def _generate_outputs(self, results: List[Dict], best_result: Optional[Dict]) -> Dict[str, Path]:
        """Generate output files.

        Args:
            results: Sorted list of results
            best_result: Best result dictionary

        Returns:
            Dictionary mapping file type to file path
        """
        # Create output directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(self.config.output_dir) / f"grid_search_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_files = {}

        # 1. Save all results to CSV
        grid_results_path = output_dir / "grid_results.csv"
        self._save_grid_results_csv(results, grid_results_path)
        output_files["grid_results"] = grid_results_path

        # 2. Save top N results to CSV
        top_n = min(self.config.top_n, len(results))
        top_results_path = output_dir / f"top_{top_n}_results.csv"
        self._save_grid_results_csv(results[:top_n], top_results_path)
        output_files["top_results"] = top_results_path

        # 3. Save best params as JSON
        if best_result:
            best_params_path = output_dir / "best_params.json"
            with open(best_params_path, 'w') as f:
                json.dump(best_result["params"], f, indent=2)
            output_files["best_params"] = best_params_path

            # 4. Save best merged config
            best_config_path = output_dir / "best_merged_config.json"
            best_config = self._merge_config(best_result["params"])
            best_config.to_json(str(best_config_path))
            output_files["best_config"] = best_config_path

        self.logger.info(f"\nOutput files saved to: {output_dir}")
        for file_type, file_path in output_files.items():
            self.logger.info(f"  {file_type}: {file_path.name}")

        return output_files

    def _save_grid_results_csv(self, results: List[Dict], filepath: Path):
        """Save results to CSV file.

        Args:
            results: List of result dictionaries
            filepath: Output file path
        """
        rows = []
        for result in results:
            row = {}
            # Add parameters
            for key, value in result["params"].items():
                row[f"param_{key}"] = value
            # Add metrics
            for key, value in result["metrics"].items():
                row[f"metric_{key}"] = value
            rows.append(row)

        df = pd.DataFrame(rows)
        df.to_csv(filepath, index=False)

    def _print_best_results(self, top_results: List[Dict]):
        """Print top results summary.

        Args:
            top_results: List of top N results
        """
        print("\n" + "=" * 70)
        print(f"TOP {len(top_results)} PARAMETER COMBINATIONS")
        print("=" * 70)
        print(f"Objective: {self.config.objective}")
        print()

        for i, result in enumerate(top_results, 1):
            obj_value = result["metrics"].get(self.config.objective, 0)
            print(f"{i}. {self.config.objective} = {obj_value:.4f}")
            print(f"   Parameters: {result['params']}")
            print(f"   Total Trades: {result['metrics'].get('total_trades', 0)}")
            print(f"   Win Rate: {result['metrics'].get('win_rate', 0) * 100:.2f}%")
            print()

        print("=" * 70)


# Worker function for parallel processing
def _evaluate_combination_worker(
    config: BacktestConfig,
    params: Dict,
    index: int,
    total: int
) -> Optional[Dict]:
    """Worker function for parallel evaluation.

    This runs in a separate process.

    Args:
        config: Base backtest configuration
        params: Parameter overrides
        index: Combination index
        total: Total combinations

    Returns:
        Result dictionary or None if failed
    """
    try:
        # Create merged config
        config_dict = copy.deepcopy(config.__dict__)
        for key, value in params.items():
            config_dict[key] = value
        merged_config = BacktestConfig(**config_dict)

        # Create data source
        data_source = BarDataSource(
            source=merged_config.source,
            symbol=merged_config.symbol,
            timeframe=merged_config.timeframe,
            start_date=merged_config.start_date,
            end_date=merged_config.end_date,
            bars=merged_config.bars,
            file_path=merged_config.file_path
        )

        # Create API client and broker
        pip_value = 0.0001 if "JPY" not in merged_config.symbol else 0.01

        api_client = SignalApiClient(
            base_url=merged_config.api_url,
            timeout=merged_config.api_timeout,
            max_retries=merged_config.api_max_retries
        )

        broker = BrokerSimulator(
            spread_pips=merged_config.spread_pips,
            slippage_pips=merged_config.slippage_pips,
            commission_per_side_per_lot=merged_config.commission_per_side_per_lot,
            usd_per_pip_per_lot=merged_config.usd_per_pip_per_lot,
            pip_value=pip_value
        )

        # Run walk-forward
        engine = WalkForwardEngine(merged_config, data_source, api_client, broker)
        wf_results = engine.run()

        # Extract metrics
        metrics = wf_results["aggregate"]

        # Cleanup
        api_client.close()

        return {
            "params": params,
            "metrics": metrics,
            "by_year": wf_results["by_year"]
        }

    except Exception as e:
        print(f"Error in worker {index}/{total}: {e}")
        return None
