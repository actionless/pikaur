# Licensed under GPLv3, see https://www.gnu.org/licenses/

LANGS := fr ru pt pt_BR de is tr da nl es zh_CN it ja uk sv

LOCALEDIR := locale
POTFILE := $(LOCALEDIR)/pikaur.pot
POFILES := $(addprefix $(LOCALEDIR)/,$(addsuffix .po,$(LANGS)))
POTEMPFILES := $(addprefix $(LOCALEDIR)/,$(addsuffix .po~,$(LANGS)))
MOFILES = $(POFILES:.po=.mo)
DISTDIR := dist

# A $(which python) is necessary here to avoid a bug in make
# that would try to execute a directory named "python".
# See https://savannah.gnu.org/bugs/?57962
PYTHON := $(shell which python)
ifeq (,$(PYTHON))
$(error Can't find Python)
endif

PIKAMAN := $(PYTHON) ./maintenance_scripts/pikaman.py
README_FILE := README.md
MAN_FILE := pikaur.1


all: locale man bin

locale: $(MOFILES)
man: $(MAN_FILE)
bin: $(DISTDIR)/usr/bin/pikaur

$(POTFILE):
	# find pikaur -type f -name '*.py' -not -name 'argparse.py' \
		#
	find pikaur -type f -name '*.py' -print0 \
		| xargs --null xgettext --language=python --add-comments --sort-by-file \
			--default-domain=pikaur --from-code=UTF-8 \
			--keyword='translate' --keyword='translate_many:1,2' \
			--output=$@

$(LOCALEDIR)/%.po: $(POTFILE)
	test -f $@ || msginit --locale=$* --no-translator --input=$< --output=$@
	msgmerge --sort-by-file --update $@ $<

%.mo: %.po
	msgfmt -o $@ $<

$(MAN_FILE): $(README_FILE)
	$(PIKAMAN) $< $@
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

clean:
	$(RM) $(LANGS_MO)
	$(RM) $(POTEMPFILES)
	$(RM) $(MAN_FILE)
	$(RM) -r $(DISTDIR)

.PHONY: all clean $(POTFILE) man bin locale $(DISTDIR)/usr/bin/pikaur $(MAN_FILE)
.PRECIOUS: $(LOCALEDIR)/%.po
