# Mathematical model notes

## Imported recipe coefficients

Normalized importer datasets store each recipe coefficient as `a_ir`, the net
production coefficient for item or fluid `i` in recipe `r`.

- `a_ir > 0` means recipe `r` outputs item `i`.
- `a_ir < 0` means recipe `r` consumes item `i`.

This matches the project-wide balance convention:

```text
sum_r a_ir * x_r + external_supply_i = final_demand_i
```
