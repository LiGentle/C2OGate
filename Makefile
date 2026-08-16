PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
PEP_PYTHONPATH ?= /tmp/c2o-mpc-deps:src

.PHONY: check-python check-ruff te-smoke study transcript-study pep-scaling-study generic-pep-scaling-study generic-pep-dual h10-generic-pep-dual h10-marginal-certificate h10-envelope-profiles h10-envelope-family scs-recovery-diagnostic sympy-exact-crosscheck joint-only-certificate exact-shift-joint-only-h10 full-class-joint-only-certificate h6-joint-only-certificate h6-medium-radius-certificate h6-independent-consumer consumer-differential-fuzz solver-benchmark pepit-comparison pepit-verified-baseline padded-model-crosscheck joint-marginal-comparison signed-boundary-audit rolling-logistic-workload uci-wdbc-benchmark measured-heat-inverse h15-scaling-diagnostic batched-parameterized-scaling synthetic-data-fixture nonlinear-pep-acceptance certificate-cost-study h10-certificate-cost-study h6-certificate-cost-study spx-sensitivity-study real-spx-study real-spx-positive-study rational-certificates studies validation-studies test verify mpc-paper mpc-source software-archive cover-letter submission check clean

check-python:
	@$(PYTHON) -c 'import sys; required=(3, 11); current=sys.version_info[:2]; sys.exit("C2OGate requires Python 3.11 or later; found %d.%d" % current) if current < required else print("Python version check: %d.%d" % current)'

check-ruff:
	@$(PYTHON) -c 'from importlib.metadata import version; current=version("ruff"); assert current == "0.12.10", "ruff==0.12.10 required, found " + current; print("ruff version: " + current)'

te-smoke: check-python check-ruff
	$(PYTHON) -m py_compile src/c2ogate/workflow.py src/c2ogate/exact_membership.py
	$(PYTHON) -m ruff check src/c2ogate/workflow.py src/c2ogate/exact_membership.py tests/test_workflow.py tests/test_exact_membership.py tests/test_uci_wdbc_gate_benchmark.py
	$(PYTHON) tools/verify_h6_joint_only_pep_dual.py certificates/h6_joint_only_pep_dual.json --root .
	PYTHONPATH=src $(PYTHON) -m pytest -q tests/test_workflow.py tests/test_exact_membership.py tests/test_uci_wdbc_gate_benchmark.py

study transcript-study pep-scaling-study generic-pep-scaling-study generic-pep-dual h10-generic-pep-dual h10-marginal-certificate h10-envelope-profiles h10-envelope-family scs-recovery-diagnostic sympy-exact-crosscheck joint-only-certificate full-class-joint-only-certificate solver-benchmark pepit-comparison pepit-verified-baseline padded-model-crosscheck joint-marginal-comparison signed-boundary-audit rolling-logistic-workload uci-wdbc-benchmark h15-scaling-diagnostic batched-parameterized-scaling synthetic-data-fixture nonlinear-pep-acceptance certificate-cost-study h10-certificate-cost-study spx-sensitivity-study real-spx-study real-spx-positive-study rational-certificates test verify mpc-paper check: check-python

study:
	$(PYTHON) experiments/run_study.py
	$(PYTHON) experiments/build_mpc_assets.py

transcript-study:
	PYTHONPATH=$(PEP_PYTHONPATH) MPLCONFIGDIR=/tmp/c2o-matplotlib $(PYTHON) experiments/run_transcript_pep_study.py
	$(PYTHON) experiments/build_mpc_assets.py

pep-scaling-study:
	PYTHONPATH=$(PEP_PYTHONPATH) MPLCONFIGDIR=/tmp/c2o-matplotlib $(PYTHON) experiments/run_pep_scaling_study.py
	$(PYTHON) experiments/build_mpc_assets.py

generic-pep-scaling-study:
	PYTHONPATH=$(PEP_PYTHONPATH) $(PYTHON) experiments/run_generic_pep_scaling_study.py
	$(PYTHON) experiments/build_mpc_assets.py

nonlinear-pep-acceptance:
	PYTHONPATH=$(PEP_PYTHONPATH) MPLCONFIGDIR=/tmp/c2o-matplotlib $(PYTHON) experiments/run_nonlinear_joint_pep_acceptance.py
	$(PYTHON) tools/verify_nonlinear_joint_pep_acceptance.py results/nonlinear_joint_pep_acceptance.json --root .
	$(PYTHON) experiments/build_mpc_assets.py

generic-pep-dual:
	PYTHONPATH=$(PEP_PYTHONPATH) $(PYTHON) experiments/generate_generic_pep_dual_certificate.py
	$(PYTHON) tools/verify_generic_nonquadratic_pep_dual.py certificates/generic_nonquadratic_pep_dual.json --root .

h10-generic-pep-dual:
	PYTHONPATH=$(PEP_PYTHONPATH) $(PYTHON) experiments/generate_h10_generic_pep_dual_certificate.py
	$(PYTHON) tools/verify_h10_generic_pep_dual.py certificates/h10_generic_pep_dual.json --root .

h10-marginal-certificate:
	PYTHONPATH=experiments $(PYTHON) experiments/generate_h10_marginal_certificate.py
	$(PYTHON) tools/verify_h10_marginal_pep_dual.py certificates/h10_marginal_pep_dual.json --root .

h10-envelope-profiles:
	PYTHONPATH=experiments $(PYTHON) experiments/generate_h10_envelope_profile.py candidate_heavy
	PYTHONPATH=experiments $(PYTHON) experiments/generate_h10_envelope_profile.py tight_contract

h10-envelope-family: h10-envelope-profiles
	$(PYTHON) experiments/build_h10_envelope_family.py
	$(PYTHON) tools/verify_h10_envelope_family.py certificates/h10_envelope_family.json --root .

scs-recovery-diagnostic:
	PYTHONPATH=experiments $(PYTHON) experiments/run_scs_recovery_diagnostic.py
	$(PYTHON) tools/verify_scs_recovery_diagnostic.py results/scs_recovery_diagnostic.json --root .

sympy-exact-crosscheck:
	$(PYTHON) experiments/run_sympy_exact_crosscheck.py

joint-only-certificate:
	$(PYTHON) experiments/generate_joint_only_shift_certificate.py
	$(PYTHON) tools/verify_joint_only_shift_certificate.py certificates/joint_only_shift_certificate.json --root .

full-class-joint-only-certificate:
	PYTHONPATH=$(PEP_PYTHONPATH):experiments $(PYTHON) experiments/generate_full_class_joint_only_pep_dual_certificate.py
	$(PYTHON) tools/verify_full_class_joint_only_pep_dual.py certificates/full_class_joint_only_pep_dual.json --root .

h6-joint-only-certificate:
	PYTHONPATH=$(PEP_PYTHONPATH):experiments $(PYTHON) experiments/generate_h6_joint_only_pep_dual_certificate.py
	$(PYTHON) tools/verify_h6_joint_only_pep_dual.py certificates/h6_joint_only_pep_dual.json --root .

h6-medium-radius-certificate:
	PYTHONPATH=$(PEP_PYTHONPATH):experiments $(PYTHON) experiments/generate_h6_joint_only_pep_dual_certificate.py --contract-radius 7/500 --schema c2o-h6-medium-radius-pep-dual-v1 --output certificates/h6_medium_radius_pep_dual.json --verifier tools/verify_h6_joint_only_pep_dual.py
	$(PYTHON) tools/verify_h6_medium_radius_pep_dual.py certificates/h6_medium_radius_pep_dual.json --root .

h6-independent-consumer:
	$(PYTHON) tools/verify_h6_sympy_independent.py certificates/h6_joint_only_pep_dual.json --output results/h6_sympy_independent_consumer.json

consumer-differential-fuzz:
	PYTHONPATH=src:experiments $(PYTHON) experiments/run_consumer_differential_fuzz.py

exact-shift-joint-only-h10:
	$(PYTHON) experiments/generate_exact_shift_joint_only_h10.py
	$(PYTHON) tools/verify_exact_shift_joint_only_h10.py certificates/exact_shift_joint_only_h10.json --root .

solver-benchmark:
	PYTHONPATH=$(PEP_PYTHONPATH) MPLCONFIGDIR=/tmp/c2o-matplotlib $(PYTHON) experiments/run_generic_pep_solver_benchmark.py
	$(PYTHON) experiments/build_mpc_assets.py

pepit-comparison:
	PYTHONPATH=src MPLCONFIGDIR=/tmp/c2o-matplotlib $(PYTHON) experiments/run_pepit_backend_comparison.py
	$(PYTHON) experiments/build_mpc_assets.py

pepit-verified-baseline:
	PYTHONPATH=src:experiments $(PYTHON) experiments/run_pepit_verified_baseline.py
	PYTHONPATH=. $(PYTHON) tools/verify_pepit_h6_baseline.py results/pepit_verified_baseline.json
	$(PYTHON) experiments/build_mpc_assets.py

joint-marginal-comparison:
	MPLCONFIGDIR=/tmp/c2o-matplotlib $(PYTHON) experiments/run_joint_marginal_capability_comparison.py
	$(PYTHON) experiments/build_mpc_assets.py

signed-boundary-audit:
	$(PYTHON) experiments/run_signed_boundary_audit.py
	$(PYTHON) experiments/build_mpc_assets.py

padded-model-crosscheck:
	PYTHONPATH=src:experiments $(PYTHON) experiments/run_padded_model_crosscheck.py
	$(PYTHON) experiments/build_mpc_assets.py

rolling-logistic-workload:
	PYTHONPATH=src $(PYTHON) experiments/run_rolling_logistic_workload.py
	$(PYTHON) experiments/build_mpc_assets.py

uci-wdbc-benchmark:
	PYTHONPATH=src:experiments $(PYTHON) experiments/run_uci_wdbc_gate_benchmark.py
	$(PYTHON) experiments/build_mpc_assets.py

measured-heat-inverse:
	PYTHONPATH=src $(PYTHON) experiments/run_measured_heat_inverse_benchmark.py
	$(PYTHON) experiments/build_mpc_assets.py

h15-scaling-diagnostic:
	PYTHONPATH=src:experiments MPLCONFIGDIR=/tmp/c2o-matplotlib $(PYTHON) experiments/run_h15_scaling_diagnostic.py
	$(PYTHON) experiments/build_mpc_assets.py

batched-parameterized-scaling:
	PYTHONPATH=src:experiments MPLCONFIGDIR=/tmp/c2o-matplotlib $(PYTHON) experiments/run_batched_parameterized_scaling.py
	$(PYTHON) experiments/build_mpc_assets.py

synthetic-data-fixture:
	$(PYTHON) experiments/generate_synthetic_data_to_matrix_fixture.py

certificate-cost-study: generic-pep-dual
	PYTHONPATH=$(PEP_PYTHONPATH) $(PYTHON) experiments/run_certificate_cost_study.py

h10-certificate-cost-study:
	$(PYTHON) experiments/run_h10_certificate_cost_study.py
	$(PYTHON) experiments/build_mpc_assets.py

h6-certificate-cost-study:
	$(PYTHON) experiments/run_h6_certificate_cost_study.py
	$(PYTHON) experiments/build_mpc_assets.py

spx-sensitivity-study:
	$(PYTHON) experiments/run_spx_sensitivity_study.py
	$(PYTHON) experiments/build_mpc_assets.py

real-spx-study:
	$(PYTHON) experiments/run_real_spx_case_study.py
	$(PYTHON) experiments/build_mpc_assets.py

real-spx-positive-study:
	PYTHONPATH=. $(PYTHON) experiments/run_real_spx_ill_conditioned_study.py
	$(PYTHON) tools/verify_real_spx_ill_conditioned_certificate.py results/real_spx_ill_conditioned_study.json
	$(PYTHON) experiments/build_mpc_assets.py

rational-certificates:
	$(PYTHON) experiments/generate_rational_dual_certificates.py
	$(PYTHON) tools/verify_rational_dual_certificates.py certificates/rational_sdp_dual_certificates.json

studies: study transcript-study pep-scaling-study generic-pep-scaling-study generic-pep-dual joint-only-certificate exact-shift-joint-only-h10 full-class-joint-only-certificate solver-benchmark pepit-comparison rolling-logistic-workload synthetic-data-fixture nonlinear-pep-acceptance rational-certificates

validation-studies: padded-model-crosscheck pepit-verified-baseline joint-marginal-comparison signed-boundary-audit uci-wdbc-benchmark measured-heat-inverse h15-scaling-diagnostic

test:
	PYTHONPATH=src $(PYTHON) -m pytest -q tests

verify:
	$(PYTHON) tools/verify_generic_nonquadratic_pep_dual.py certificates/generic_nonquadratic_pep_dual.json --root .
	$(PYTHON) tools/verify_h10_generic_pep_dual.py certificates/h10_generic_pep_dual.json --root .
	$(PYTHON) tools/verify_h10_marginal_pep_dual.py certificates/h10_marginal_pep_dual.json --root .
	$(PYTHON) tools/verify_h10_envelope_family.py certificates/h10_envelope_family.json --root .
	$(PYTHON) tools/verify_scs_recovery_diagnostic.py results/scs_recovery_diagnostic.json --root .
	$(PYTHON) tools/verify_joint_only_shift_certificate.py certificates/joint_only_shift_certificate.json --root .
	$(PYTHON) tools/verify_full_class_joint_only_pep_dual.py certificates/full_class_joint_only_pep_dual.json --root .
	$(PYTHON) tools/verify_h6_joint_only_pep_dual.py certificates/h6_joint_only_pep_dual.json --root .
	$(PYTHON) tools/verify_h6_medium_radius_pep_dual.py certificates/h6_medium_radius_pep_dual.json --root .
	PYTHONPATH=. $(PYTHON) tools/verify_pepit_h6_baseline.py results/pepit_verified_baseline.json
	$(PYTHON) tools/verify_h6_sympy_independent.py certificates/h6_joint_only_pep_dual.json
	$(PYTHON) tools/verify_exact_shift_joint_only_h10.py certificates/exact_shift_joint_only_h10.json --root .
	$(PYTHON) tools/verify_rational_dual_certificates.py certificates/rational_sdp_dual_certificates.json
	$(PYTHON) tools/verify_real_spx_ill_conditioned_certificate.py results/real_spx_ill_conditioned_study.json
	$(PYTHON) tools/verify_nonlinear_joint_pep_acceptance.py results/nonlinear_joint_pep_acceptance.json --root .

mpc-paper: verify
	$(PYTHON) experiments/build_mpc_assets.py
	cd paper_mpc && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
	mkdir -p output/pdf
	cp paper_mpc/main.pdf output/pdf/c2ogate_mpc_manuscript.pdf

cover-letter:
	cd cover_letter && latexmk -pdf -interaction=nonstopmode -halt-on-error cover_letter.tex
	mkdir -p output/pdf
	cp cover_letter/cover_letter.pdf output/pdf/mpc_cover_letter.pdf

mpc-source: mpc-paper
	zip -q -FS output/mpc_latex_source.zip \
		paper_mpc/main.tex paper_mpc/main.bbl paper_mpc/references.bib \
		paper_mpc/svjour3.cls paper_mpc/svglov3.clo paper_mpc/spmpsci.bst \
		paper_mpc/generated/metrics.tex \
		figures/generic_pep_solver_benchmark.pdf \
		figures/joint_vs_marginal_rectangle.pdf

software-archive:
	zip -q -r -FS output/c2ogate_mpc_artifact.zip \
		README.md REUSABILITY_CONTRACT.md ARTIFACT_EVALUATION.md LICENSE CITATION.cff pyproject.toml environment.yml Makefile \
		.github src examples experiments tools tests results certificates figures data \
		-x '*/__pycache__/*' '*.pyc' '*.DS_Store' 'src/*.egg-info/*' \
		'figures/c2o_study.pdf' 'figures/transcript_pep_study.pdf' \
		'figures/transcript_pep_study.png'

submission: mpc-source software-archive cover-letter

check:
	$(PYTHON) -m py_compile src/c2ogate/*.py examples/*.py experiments/*.py tools/*.py
	$(PYTHON) -m ruff check src experiments tools tests
	PYTHONPATH=src $(PYTHON) -m pytest -q tests

check: check-ruff

clean:
	cd paper_mpc && latexmk -C
	cd cover_letter && latexmk -C
