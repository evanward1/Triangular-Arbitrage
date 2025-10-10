import json
import time
from collections import deque
from pathlib import Path
from typing import Dict, List


class GNNArbitrageOptimizer:
    def __init__(
        self, state_file="logs/gnn_state.json", memory_size=1000, learning_rate=0.01
    ):
        self.state_file = Path(state_file)
        self.memory_size = memory_size
        self.learning_rate = learning_rate
        self.trade_history = deque(maxlen=memory_size)
        self.edge_weights = {}
        self.node_features = {}
        self.profit_predictions = {}
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.load_state()

    def load_state(self):
        if self.state_file.exists():
            with open(self.state_file, "r") as f:
                data = json.load(f)
                self.edge_weights = data.get("edge_weights", {})
                self.node_features = data.get("node_features", {})
                self.profit_predictions = data.get("profit_predictions", {})

    def save_state(self):
        data = {
            "edge_weights": self.edge_weights,
            "node_features": self.node_features,
            "profit_predictions": self.profit_predictions,
            "last_updated": time.time(),
        }
        with open(self.state_file, "w") as f:
            json.dump(data, f)

    def add_trade_result(
        self,
        cycle: List[str],
        expected_profit: float,
        actual_profit: float,
        execution_time: float,
    ):
        cycle_key = "->".join(cycle)
        self.trade_history.append(
            {
                "cycle": cycle,
                "cycle_key": cycle_key,
                "expected_profit": expected_profit,
                "actual_profit": actual_profit,
                "execution_time": execution_time,
                "timestamp": time.time(),
            }
        )
        self._update_graph_features(
            cycle, expected_profit, actual_profit, execution_time
        )
        self._update_predictions(cycle_key, expected_profit, actual_profit)

    def _update_graph_features(
        self,
        cycle: List[str],
        expected_profit: float,
        actual_profit: float,
        execution_time: float,
    ):
        for i in range(len(cycle)):
            node = cycle[i]
            if node not in self.node_features:
                self.node_features[node] = {
                    "trade_count": 0,
                    "total_profit": 0.0,
                    "avg_execution_time": 0.0,
                }
            self.node_features[node]["trade_count"] += 1
            self.node_features[node]["total_profit"] += actual_profit
            current_avg = self.node_features[node]["avg_execution_time"]
            count = self.node_features[node]["trade_count"]
            self.node_features[node]["avg_execution_time"] = (
                current_avg * (count - 1) + execution_time
            ) / count
            next_node = cycle[(i + 1) % len(cycle)]
            edge_key = f"{node}->{next_node}"
            if edge_key not in self.edge_weights:
                self.edge_weights[edge_key] = {
                    "weight": 1.0,
                    "success_rate": 0.5,
                    "count": 0,
                }
            self.edge_weights[edge_key]["count"] += 1
            success = 1.0 if actual_profit > 0 else 0.0
            current_rate = self.edge_weights[edge_key]["success_rate"]
            count = self.edge_weights[edge_key]["count"]
            self.edge_weights[edge_key]["success_rate"] = (
                current_rate * (count - 1) + success
            ) / count
            error = expected_profit - actual_profit
            self.edge_weights[edge_key]["weight"] -= self.learning_rate * error

    def _update_predictions(
        self, cycle_key: str, expected_profit: float, actual_profit: float
    ):
        if cycle_key not in self.profit_predictions:
            self.profit_predictions[cycle_key] = {
                "predicted_profit": expected_profit,
                "actual_avg": actual_profit,
                "count": 1,
            }
        else:
            count = self.profit_predictions[cycle_key]["count"]
            current_avg = self.profit_predictions[cycle_key]["actual_avg"]
            self.profit_predictions[cycle_key]["actual_avg"] = (
                current_avg * count + actual_profit
            ) / (count + 1)
            self.profit_predictions[cycle_key]["count"] += 1
            self.profit_predictions[cycle_key][
                "predicted_profit"
            ] = self.profit_predictions[cycle_key]["actual_avg"]

    def predict_profit(self, cycle: List[str], base_profit: float) -> float:
        cycle_key = "->".join(cycle)
        if cycle_key in self.profit_predictions:
            historical_avg = self.profit_predictions[cycle_key]["actual_avg"]
            predicted = self.profit_predictions[cycle_key]["predicted_profit"]
            return predicted * 0.7 + historical_avg * 0.3
        edge_adjustment = 1.0
        for i in range(len(cycle)):
            next_node = cycle[(i + 1) % len(cycle)]
            edge_key = f"{cycle[i]}->{next_node}"
            if edge_key in self.edge_weights:
                edge_adjustment *= self.edge_weights[edge_key]["success_rate"]
        return base_profit * edge_adjustment

    def get_cycle_score(self, cycle: List[str]) -> float:
        cycle_key = "->".join(cycle)
        score = 1.0
        if cycle_key in self.profit_predictions:
            count = self.profit_predictions[cycle_key]["count"]
            avg_profit = self.profit_predictions[cycle_key]["actual_avg"]
            score += (avg_profit / 100.0) * min(count / 10.0, 1.0)
        for i in range(len(cycle)):
            next_node = cycle[(i + 1) % len(cycle)]
            edge_key = f"{cycle[i]}->{next_node}"
            if edge_key in self.edge_weights:
                score *= self.edge_weights[edge_key]["success_rate"]
        return score

    def get_statistics(self) -> Dict:
        return {
            "total_trades": len(self.trade_history),
            "unique_cycles": len(self.profit_predictions),
            "tracked_edges": len(self.edge_weights),
            "tracked_nodes": len(self.node_features),
        }
