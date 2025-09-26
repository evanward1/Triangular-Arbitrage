# Grafana Dashboard Setup for Triangular Arbitrage

This document provides configuration for monitoring triangular arbitrage trading with Grafana and Prometheus.

## Prometheus Configuration

Add this job to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'triangular-arbitrage'
    static_configs:
      - targets: ['localhost:8000']
    scrape_interval: 10s
    metrics_path: '/metrics'
    scrape_timeout: 5s
```

## Key Metrics Available

### Cycle Performance
- `triangular_arbitrage_cycles_started_total` - Total cycles started
- `triangular_arbitrage_cycles_filled_total` - Successfully completed cycles
- `triangular_arbitrage_cycles_canceled_by_slippage_total` - Slippage cancellations
- `triangular_arbitrage_cycles_canceled_by_latency_total` - Latency cancellations
- `triangular_arbitrage_cycles_partial_filled_total` - Partial fills

### Profitability
- `triangular_arbitrage_realized_profit_basis_points` - Per-cycle profits in bps
- `triangular_arbitrage_total_profit_loss` - Cumulative P&L by currency
- `triangular_arbitrage_execution_fees_total` - Total fees paid

### Execution Quality
- `triangular_arbitrage_leg_latency_seconds` - Individual leg latencies
- `triangular_arbitrage_cycle_duration_seconds` - Complete cycle durations
- `triangular_arbitrage_slippage_basis_points` - Order slippage
- `triangular_arbitrage_order_fill_ratio` - Fill rate

### Risk Controls
- `triangular_arbitrage_cooldown_count` - Active cooldowns
- `triangular_arbitrage_risk_violations_total` - Risk violations
- `triangular_arbitrage_consecutive_losses` - Current loss streak

## Example Grafana Queries

### Success Rate Panel
```
rate(triangular_arbitrage_cycles_filled_total[5m]) / rate(triangular_arbitrage_cycles_started_total[5m]) * 100
```

### Average Profit per Cycle
```
rate(triangular_arbitrage_realized_profit_basis_points_sum[5m]) / rate(triangular_arbitrage_realized_profit_basis_points_count[5m])
```

### P95 Cycle Latency
```
histogram_quantile(0.95, rate(triangular_arbitrage_cycle_duration_seconds_bucket[5m]))
```

### Active Positions
```
sum by (currency) (triangular_arbitrage_active_balance{execution_mode="live"})
```

### Risk Violations Rate
```
rate(triangular_arbitrage_risk_violations_total[1h])
```

### Fill Rate by Mode
```
rate(triangular_arbitrage_orders_filled_total[5m]) / rate(triangular_arbitrage_orders_placed_total[5m]) * 100
```

## Dashboard Layout Recommendations

### Row 1: Overview
- Total cycles today
- Success rate (%)
- Total P&L today
- Average profit per cycle

### Row 2: Performance
- Cycle completion rate over time
- P95/P99 latency trends
- Slippage distribution
- Fill rate by execution mode

### Row 3: Risk Management
- Active cooldowns
- Risk violations timeline
- Consecutive losses alert
- Position sizes by currency

### Row 4: System Health
- Strategy uptime
- Last activity timestamp
- Error rates
- Balance trends

## Alerts Configuration

### Critical Alerts
```yaml
- alert: ArbitrageNoActivity
  expr: time() - triangular_arbitrage_last_activity_timestamp > 300
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "No trading activity for {{ $labels.strategy_name }}"

- alert: HighConsecutiveLosses
  expr: triangular_arbitrage_consecutive_losses >= 5
  for: 1m
  labels:
    severity: warning
  annotations:
    summary: "High consecutive losses: {{ $value }}"

- alert: LowFillRate
  expr: rate(triangular_arbitrage_orders_filled_total[10m]) / rate(triangular_arbitrage_orders_placed_total[10m]) < 0.8
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Low order fill rate: {{ $value | humanizePercentage }}"
```

### Warning Alerts
```yaml
- alert: HighSlippage
  expr: histogram_quantile(0.95, rate(triangular_arbitrage_slippage_basis_points_bucket[5m])) > 20
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "High P95 slippage: {{ $value }} bps"

- alert: HighLatency
  expr: histogram_quantile(0.95, rate(triangular_arbitrage_leg_latency_seconds_bucket[5m])) > 1.0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "High P95 leg latency: {{ $value }}s"
```

## Sample Grafana Dashboard JSON

```json
{
  "dashboard": {
    "title": "Triangular Arbitrage Trading",
    "panels": [
      {
        "title": "Cycle Success Rate",
        "type": "stat",
        "targets": [
          {
            "expr": "rate(triangular_arbitrage_cycles_filled_total[5m]) / rate(triangular_arbitrage_cycles_started_total[5m]) * 100",
            "legendFormat": "Success Rate %"
          }
        ]
      },
      {
        "title": "Cycles per Hour",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(triangular_arbitrage_cycles_started_total[1h]) * 3600",
            "legendFormat": "{{strategy_name}} - {{execution_mode}}"
          }
        ]
      },
      {
        "title": "Profit Distribution",
        "type": "histogram",
        "targets": [
          {
            "expr": "triangular_arbitrage_realized_profit_basis_points",
            "legendFormat": "Profit (bps)"
          }
        ]
      }
    ]
  }
}
```

## Testing Metrics

Verify metrics are working:

```bash
# Check metrics endpoint
curl http://localhost:8000/metrics

# Check health endpoint
curl http://localhost:8000/health

# Test with specific queries
curl 'http://localhost:9090/api/v1/query?query=triangular_arbitrage_cycles_started_total'
```

## Troubleshooting

### Metrics Not Appearing
1. Check if metrics server is running on correct port
2. Verify Prometheus scrape configuration
3. Check firewall/network connectivity
4. Review application logs for errors

### High Memory Usage
- Metrics with high cardinality (many label combinations) can consume memory
- Consider reducing label dimensions if needed
- Monitor Prometheus memory usage

### Grafana Connection Issues
- Verify Prometheus data source configuration
- Check query syntax in Grafana
- Use Grafana's built-in query builder for testing