# Exact rational SDP dual certificates

`rational_sdp_dual_certificates.json` contains nine dual certificates for
three accepted rational quadratic transcript instances.  Verification does
not use CVXPY, Clarabel, NumPy, `mpmath`, eigenvalue tolerances, or solver
status.  It requires only Python 3.11 or later:

Schema v2 stores the rational current witness `x` and candidate
`y=(I-alpha Q)^d x`.  Before accepting any dual bound, the verifier checks
`x^T x=1` and the shift identity in exact arithmetic.  These are payload data,
not unstated generator assumptions.

```bash
python tools/verify_rational_dual_certificates.py \
  certificates/rational_sdp_dual_certificates.json
```

The expected result is:

```text
VERIFIED: 3 instances, 9 rational SDP dual certificates, 87 exact principal minors
```

For iteration `k`, the verifier recomputes

```text
C_k = (A^k)^T Q^2 A^k,    A = I - alpha Q,
```

and checks the exact dual identity

```text
C_k = nu_k I + Z_k,    Z_k positive semidefinite,    nu_k > epsilon^2.
```

All data are parsed as `fractions.Fraction`.  Positive semidefiniteness is
proved by exact nonnegativity of every principal minor of `Z_k`.  The verifier
also checks the rational eigendecomposition of `Q`, contraction conditions,
the stored witness and candidate, the complete range `k = 0,...,d-1`, call
saving, total-cost acceptance, stored minor minima, declared counts, and the
canonical payload hash.

The 110-decimal-digit computation in
`experiments/generate_rational_dual_certificates.py` is only a proposal
mechanism.  Its output is accepted only after the independent exact checks.
Regenerate and verify with:

```bash
make rational-certificates
```

Frozen canonical payload hash:

```text
1b9f47487cfc4fc9369695f0b6130da253a4074fde91aa62aef0ef89ca2d17b0
```

## Generic nonquadratic joint-PEP dual

`generic_nonquadratic_pep_dual.json` is a separate exact certificate for the
generic cost-violating cell `(3,3)` in the horizon-three non-shift,
nonquadratic acceptance example. Its standard-library verifier reconstructs
the complete Gram SDP (10 vector atoms, 9 function values, 86 interpolation
and cell inequalities, and one equality), then checks nonnegative rational
dual multipliers, exact stationarity, the slack identity, a strictly negative
dual objective, and ten positive leading principal minors:

```bash
python tools/verify_generic_nonquadratic_pep_dual.py \
  certificates/generic_nonquadratic_pep_dual.json
```

Expected result:

```text
VERIFIED: generic nonquadratic H=3 joint-PEP dual, cell (3, 3), upper bound < 0, 10 positive leading principal minors
```

The CVXPY--Clarabel run in
`experiments/generate_generic_pep_dual_certificate.py` is only a proposal
mechanism. Regenerate the proposal, recover its rational proof, and replay the
independent verifier with:

```bash
make generic-pep-dual
```
