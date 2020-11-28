# This file is licensed under GPLv3, see https://www.gnu.org/licenses/

LANGS := fr ru pt de is tr da nl es zh_CN it ja

LOCALEDIR := locale
POTFILE := $(LOCALEDIR)/pikaur.pot
POFILES := $(addprefix $(LOCALEDIR)/,$(addsuffix .po,$(LANGS)))
POTEMPFILES := $(addprefix $(LOCALEDIR)/,$(addsuffix .po~,$(LANGS)))
MOFILES = $(POFILES:.po=.mo)

PIKAMAN := python ./maintenance_scripts/pikaman.py
README_FILE := README.md
MAN_FILE := pikaur.1

all: locale man

locale: $(MOFILES)

$(POTFILE):
	# find pikaur -type f -name '*.py' -not -name 'argparse.py' \
		#
	find pikaur -type f -name '*.py' \
		| xargs xgettext --language=python --add-comments --sort-output \
			--default-domain=pikaur --from-code=UTF-8 --keyword='_n:1,2' --output=$@

$(LOCALEDIR)/%.po: $(POTFILE)
	test -f $@ || msginit --locale=$* --no-translator --input=$< --output=$@
	msgmerge --update $@ $<

%.mo: %.po
	msgfmt -o $@ $<

clean:
	$(RM) $(LANGS_MO)
	$(RM) $(POTEMPFILES)
	$(RM) $(MAN_FILE)

man:
	$(PIKAMAN) $(README_FILE) $(MAN_FILE)
	sed -i \
		-e '/travis/d' \
		-e '/Screenshot/d' \
		$(MAN_FILE)

.PHONY: all clean $(POTFILE) man
.PRECIOUS: $(LOCALEDIR)/%.po
