PYTHON ?= python
PEP_PYTHONPATH ?= /tmp/c2o-mpc-deps:src

.PHONY: study transcript-study pep-scaling-study generic-pep-scaling-study generic-pep-dual nonlinear-pep-acceptance certificate-cost-study spx-sensitivity-study real-spx-study real-spx-positive-study rational-certificates studies test verify mpc-paper mpc-source software-archive cover-letter submission check clean

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

certificate-cost-study: generic-pep-dual
	PYTHONPATH=$(PEP_PYTHONPATH) $(PYTHON) experiments/run_certificate_cost_study.py

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

studies: study transcript-study pep-scaling-study generic-pep-scaling-study generic-pep-dual nonlinear-pep-acceptance rational-certificates

test:
	PYTHONPATH=src $(PYTHON) -m pytest -q tests

verify:
	$(PYTHON) tools/verify_generic_nonquadratic_pep_dual.py certificates/generic_nonquadratic_pep_dual.json --root .
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
		paper_mpc/generated/metrics.tex figures/transcript_pep_study.pdf

software-archive:
	zip -q -r -FS output/c2ogate_mpc_artifact.zip \
		README.md ARTIFACT_EVALUATION.md LICENSE CITATION.cff pyproject.toml Makefile \
		src experiments tools tests results certificates figures \
		-x '*/__pycache__/*' '*.pyc' '*.DS_Store'

submission: mpc-source software-archive cover-letter

check:
	$(PYTHON) -m py_compile src/c2ogate/*.py experiments/*.py tools/*.py
	ruff check src experiments tools tests
	PYTHONPATH=src $(PYTHON) -m pytest -q tests

clean:
	cd paper_mpc && latexmk -C
	cd cover_letter && latexmk -C
