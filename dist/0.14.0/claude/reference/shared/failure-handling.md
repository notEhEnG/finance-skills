# Shared failure handling

| Status | Required behavior |
|---|---|
| `success` | Continue. |
| `partial` | Continue and preserve every material limitation. |
| `insufficient_data` | Stop unsupported sections and name missing inputs. |
| `provider_error` | Report failure without fixture substitution. |
| `period_mismatch` | Block affected calculations and comparisons. |
| `currency_mismatch` | Block affected calculations and comparisons. |
| `unsupported_analysis` | Explain why the analysis is unavailable. |
| `engine_error` | Report the failure and stop. |

Never guess through a typed failure.
