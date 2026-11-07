# S-02 Systems

## Depends On

| System | Use |
| --- | --- |
| Probe executor | Performs DLL calls and captures results. |
| Curriculum ordering | Chooses probe order from static/setup and prior evidence. |
| Finding persistence | Stores observed behavior and working calls. |
| Sentinel/vocab context | Interprets return values and builds arguments. |

## Does Not Own

| System | Boundary |
| --- | --- |
| Setup/static packet production | S-00 owns setup and handoff packet production. |
| Write unlock discovery | S-01 owns initial unlock attempts. |
| Reconciliation | S-03 owns deterministic repair of contradictory findings. |

## System Notes

S-02 produces runtime evidence. It should spend runtime budget on uncertainty
that earlier static/setup stages could not cheaply remove.
