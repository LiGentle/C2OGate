PYTHON ?= python3
PEP_PYTHONPATH ?= /tmp/c2o-mpc-deps:src
RUFF_VERSION ?= 0.12.10

.PHONY: check-python check-ruff study transcript-study pep-scaling-study generic-pep-scaling-study generic-pep-dual h10-generic-pep-dual joint-only-certificate full-class-joint-only-certificate solver-benchmark pepit-comparison synthetic-data-fixture nonlinear-pep-acceptance certificate-cost-study h10-certificate-cost-study spx-sensitivity-study real-spx-study real-spx-positive-study rational-certificates studies test verify mpc-paper mpc-source software-archive cover-letter submission check clean

check-python:
	@$(PYTHON) -c 'import sys; required=(3, 11); current=sys.version_info[:2]; sys.exit("C2OGate requires Python 3.11 or later; found %d.%d" % current) if current < required else print("Python version check: %d.%d" % current)'

check-ruff:
	@$(PYTHON) -c 'from importlib.metadata import version; actual=version("ruff"); expected="$(RUFF_VERSION)"; assert actual == expected, "C2OGate check requires ruff %s; found %s" % (expected, actual); print("ruff version check: %s" % actual)'

study transcript-study pep-scaling-study generic-pep-scaling-study generic-pep-dual h10-generic-pep-dual joint-only-certificate full-class-joint-only-certificate solver-benchmark pepit-comparison synthetic-data-fixture nonlinear-pep-acceptance certificate-cost-study h10-certificate-cost-study spx-sensitivity-study real-spx-study real-spx-positive-study rational-certificates test verify mpc-paper check: check-python

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

joint-only-certificate:
	$(PYTHON) experiments/generate_joint_only_shift_certificate.py
	$(PYTHON) tools/verify_joint_only_shift_certificate.py certificates/joint_only_shift_certificate.json --root .

full-class-joint-only-certificate:
	PYTHONPATH=$(PEP_PYTHONPATH):experiments $(PYTHON) experiments/generate_full_class_joint_only_pep_dual_certificate.py
	$(PYTHON) tools/verify_full_class_joint_only_pep_dual.py certificates/full_class_joint_only_pep_dual.json --root .

solver-benchmark:
	PYTHONPATH=$(PEP_PYTHONPATH) MPLCONFIGDIR=/tmp/c2o-matplotlib $(PYTHON) experiments/run_generic_pep_solver_benchmark.py
	$(PYTHON) experiments/build_mpc_assets.py

pepit-comparison:
	PYTHONPATH=$(PEP_PYTHONPATH) $(PYTHON) experiments/run_pepit_backend_comparison.py
	$(PYTHON) experiments/build_mpc_assets.py

synthetic-data-fixture:
	$(PYTHON) experiments/generate_synthetic_data_to_matrix_fixture.py

certificate-cost-study: generic-pep-dual
	PYTHONPATH=$(PEP_PYTHONPATH) $(PYTHON) experiments/run_certificate_cost_study.py

h10-certificate-cost-study:
	$(PYTHON) experiments/run_h10_certificate_cost_study.py
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

studies: study transcript-study pep-scaling-study generic-pep-scaling-study generic-pep-dual joint-only-certificate full-class-joint-only-certificate solver-benchmark pepit-comparison synthetic-data-fixture nonlinear-pep-acceptance rational-certificates

test:
	PYTHONPATH=src $(PYTHON) -m pytest -q tests

verify:
	$(PYTHON) tools/verify_generic_nonquadratic_pep_dual.py certificates/generic_nonquadratic_pep_dual.json --root .
	$(PYTHON) tools/verify_h10_generic_pep_dual.py certificates/h10_generic_pep_dual.json --root .
	$(PYTHON) tools/verify_joint_only_shift_certificate.py certificates/joint_only_shift_certificate.json --root .
	$(PYTHON) tools/verify_full_class_joint_only_pep_dual.py certificates/full_class_joint_only_pep_dual.json --root .
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
		paper_mpc/generated/metrics.tex figures/transcript_pep_study.pdf \
		figures/generic_pep_solver_benchmark.pdf

software-archive:
	zip -q -r -FS output/c2ogate_mpc_artifact.zip \
		README.md ARTIFACT_EVALUATION.md LICENSE CITATION.cff pyproject.toml environment.yml Makefile \
		src experiments tools tests results certificates figures data \
		-x '*/__pycache__/*' '*.pyc' '*.DS_Store' 'src/*.egg-info/*'

submission: mpc-source software-archive cover-letter

check:
	$(PYTHON) -m py_compile src/c2ogate/*.py experiments/*.py tools/*.py
	$(PYTHON) -m ruff check src experiments tools tests
	PYTHONPATH=src $(PYTHON) -m pytest -q tests

check: check-ruff

clean:
	cd paper_mpc && latexmk -C
	cd cover_letter && latexmk -C
