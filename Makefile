# Licensed under GPLv3, see https://www.gnu.org/licenses/

# installation:
DISTDIR := dist

# environment:
SHELL := bash
# A $(which python) is necessary here to avoid a bug in make
# that would try to execute a directory named "python".
# See https://savannah.gnu.org/bugs/?57962
PYTHON := $(shell which python)
ifeq (,$(PYTHON))
$(error Can't find Python)
endif
MINIMAL_PYTHON_VERSION := (3, 12, 3)

# locales:
LANGS := fr ru pt pt_BR de is tr da nl es zh_CN it ja uk sv
LOCALEDIR := locale
POTFILE := $(LOCALEDIR)/pikaur.pot
POFILES := $(addprefix $(LOCALEDIR)/,$(addsuffix .po,$(LANGS)))
POTEMPFILES := $(addprefix $(LOCALEDIR)/,$(addsuffix .po~,$(LANGS)))
MOFILES = $(POFILES:.po=.mo)

# lint:
RUFF := ruff
script_dir := $(shell readlink -e .)
APP_DIR := $(shell readlink -e "$(script_dir)")
TARGET_MODULE := pikaur
TARGETS := \
		   $(APP_DIR)/$(TARGET_MODULE)/ \
		   $(APP_DIR)/pikaur_test/ \
		   $(APP_DIR)/pikaur_meta_helpers/ \
		   $(APP_DIR)/packaging/usr/bin/pikaur \
		   $(shell ls $(APP_DIR)/maintenance_scripts/*.py) \
		   $(shell ls $(APP_DIR)/pikaur_static/*.py)
GLOBALS_IGNORES := \
			-e ': Final' \
			-e ' \# nonfinal-ignore' \
			-e ' \# checkglobals-ignore' \
			\
			-e TypeVar \
			-e namedtuple \
			\
			-e 'create_logger\(|sudo' \
			\
			-e './maintenance_scripts/find_.*.py.*:.*:' \
			-e '.SRCINFO'

# man:
PIKAMAN := $(PYTHON) ./maintenance_scripts/pikaman.py
README_FILE := README.md
MAN_FILE := $(TARGET_MODULE).1

################################################################################

all: checkpython locale man bin

.PHONY: all clean $(POTFILE) man bin locale $(DISTDIR)/usr/bin/pikaur $(MAN_FILE) standalone checkpython lint lint_fix compile_all python_import non_final_globals unreasonable_globals ruff flake8 pylint mypy vulture shellcheck shellcheck_makefile validate_pyproject
.PRECIOUS: $(LOCALEDIR)/%.po

################################################################################

locale: $(MOFILES)

man: $(MAN_FILE)

bin: $(DISTDIR)/usr/bin/pikaur

checkpython:
	# ensure python version is bigger or equal to $(MINIMAL_PYTHON_VERSION)
	$(PYTHON) -c 'import sys ; sys.exit(sys.version_info < $(MINIMAL_PYTHON_VERSION))'

$(POTFILE):
	find $(TARGET_MODULE) -type f -name '*.py' -print0 \
		| xargs --null xgettext --language=python --add-comments --sort-by-file \
			--default-domain=$(TARGET_MODULE) --from-code=UTF-8 \
			--keyword='translate' --keyword='translate_many:1,2' \
			--output=$@

$(LOCALEDIR)/%.po: $(POTFILE)
	test -f $@ || msginit --locale=$* --no-translator --input=$< --output=$@
	msgmerge --sort-by-file --update $@ $<

%.mo: %.po
	msgfmt -o $@ $<

$(MAN_FILE): $(README_FILE)
	$(PIKAMAN) $< $@ --name $(TARGET_MODULE)
	sed -i \
		-e '/coveralls/d' \
		-e '/Screenshot/d' \
		$@

$(DISTDIR)/usr/bin:
	mkdir -p $@

$(DISTDIR)/usr/bin/pikaur: $(DISTDIR)/usr/bin
	sed \
		-e "s/%PYTHON_BUILD_VERSION%/$$(\
			$(PYTHON) -c \
				'import sys ; \
				print(f"{sys.version_info.major}.{sys.version_info.minor}") \
		')/g" \
		packaging/usr/bin/pikaur > $@
	chmod +x $@

standalone: checkpython locale man
	cd pikaur_static && ./make.fish standalone

clean:
	$(RM) $(LANGS_MO)
	$(RM) $(POTEMPFILES)
	$(RM) $(MAN_FILE)
	$(RM) -r $(DISTDIR)

################################################################################

lint_fix:
	$(RUFF) check --fix $(TARGETS)

compile_all:
	export PYTHONWARNINGS='ignore,error:::$(TARGET_MODULE)[.*],error:::pikaur_test[.*]'
	# Running python compile:
	$(PYTHON) -O -m compileall $(TARGETS) \
	| (\
		grep -v -e '^Listing' -e '^Compiling' || true \
	)
	# :: python compile passed ::

python_import:
	# Running python import:
	$(PYTHON) -c "import $(TARGET_MODULE).main"
	# :: python import passed ::

non_final_globals:
	# Checking for non-Final globals:
	result=$$( \
		grep -REn "^[a-zA-Z_]+ = " $(TARGETS) --color=always \
		| grep -Ev \
			\
			-e '=.*\|' \
			-e '=.*(dict|list|Callable)\[' \
			\
			-e '__all__' \
			\
			$(GLOBALS_IGNORES) \
		| sort \
	) ; \
	echo -n "$$result" ; \
	exit "$$(test "$$result" = "" && echo 0 || echo 1)"
	# :: non-final globals check passed ::

unreasonable_globals:
	# Checking for unreasonable global vars:
	result=$$( \
		grep -REn "^[a-zA-Z_]+ = [^'\"].*" $(TARGETS) --color=always \
		| grep -Ev \
			\
			-e ' =.*\|' \
			-e ' = [a-zA-Z_]+\[' \
			-e ' = str[^(]' \
			\
			-e '__all__' \
			\
			$(GLOBALS_IGNORES) \
		| sort \
	) ; \
	echo -n "$$result" ; \
	exit "$$(test "$$result" = "" && echo 0 || echo 1)"
	# :: global vars check passed ::

ruff:
	# Checking Ruff rules up-to-date:
	diff --color -u \
		<(awk '/select = \[/,/]/' pyproject.toml \
			| sed -e 's|", "|/|g' \
			| head -n -1 \
			| tail -n +2 \
			| tr -d '",\#' \
			| awk '{print $$1;}' \
			| sort) \
		<($(RUFF) linter \
			| awk '{print $$1;}' \
			| sort)
	# Running ruff...
	$(RUFF) check $(TARGETS)
	# :: ruff passed ::

flake8:
	# Running flake8:
	$(PYTHON) -m flake8 $(TARGETS)
	# :: flake8 passed ::

pylint:
	# Running pylint:
	$(PYTHON) -m pylint $(TARGETS) --score no
	# :: pylint passed ::

mypy:
	# Running mypy:
	$(PYTHON) -m mypy $(TARGETS) --no-error-summary
	# :: mypy passed ::

vulture:
	# Running vulture:
	$(PYTHON) -m vulture $(TARGETS) \
		--min-confidence=1 \
		--sort-by-size
	# :: vulture passed ::

shellcheck:
	# Running shellcheck:
	find . \
		\( \
			-name '*.sh' \
			-not -wholename '*/$(TARGET_MODULE)*.*build/*' \
			-or -name 'PKGBUILD' \
		\) \
		-exec sh -c 'set -x ; shellcheck "$$@"' shellcheck {} \+
	# :: shellcheck passed ::

shellcheck_makefile:
	# Running shellcheck on Makefile...
	shellcheck_makefile --exclude SC2317
	# :: shellcheck makefile passed ::

validate_pyproject:
	# Validate pyproject file...
	( \
		exit_code=0 ; \
		result=$$(validate-pyproject pyproject.toml 2>&1) || exit_code=$$? ; \
		if [[ $$exit_code -gt 0 ]] ; then \
			echo "$$result" ; \
			exit "$$exit_code" ; \
		fi \
	)
	# :: pyproject validation passed ::

lint: compile_all python_import non_final_globals unreasonable_globals ruff flake8 pylint mypy vulture shellcheck shellcheck_makefile validate_pyproject
