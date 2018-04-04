LANGS := fr ru pt de

LOCALEDIR := locale
POTFILE := $(LOCALEDIR)/pikaur.pot
POFILES := $(addprefix $(LOCALEDIR)/,$(addsuffix .po,$(LANGS)))
MOFILES = $(POFILES:.po=.mo)

all: $(MOFILES)

$(POTFILE):
	find pikaur -type f -name '*.py' -not -name 'argparse.py' \
		| xargs xgettext --language=python --add-comments --sort-output \
			--default-domain=pikaur --from-code=UTF-8 --keyword='_n:1,2' --output=$@

$(LOCALEDIR)/%.po: $(POTFILE)
	test -f $@ || msginit --locale=$* --no-translator --input=$< --output=$@
	msgmerge --update $@ $<

%.mo: %.po
	msgfmt -o $@ $<

clean:
	$(RM) $(LANGS_MO)

.PHONY: all clean $(POTFILE)
.PRECIOUS: $(LOCALEDIR)/%.po
