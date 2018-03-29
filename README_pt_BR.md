# pikaur

Auxiliar do AUR com dependências mínimas. Revise todos os PKGBUILDs de uma só vez e, em seguida, construa todos eles com o mínimo de interação do usuário.

Inspirado por `pacaur`,` yaourt` e `yay`.

* [Instalação](#instalação "")
* [Executar sem instalação](#executar-sem-instalação"")
* [Arquivo de configuração](#configuração "")
* [Diretórios](#diretórios "")
* [Perguntas frequentes](#perguntas-frequentes "")
* [Contribuindo](#contribuindo "")
* [Traduções](#traduções "")



### Instalação

```sh
git clone https://aur.archlinux.org/pikaur.git
cd pikaur
makepkg -fsri
```


### Executar sem instalação

```sh
git clone https://github.com/actionless/pikaur.git
cd pikaur
python3 ./pikaur.py -Ss AUR_PACKAGE_NAME
python3 ./pikaur.py -S AUR_PACKAGE_NAME
python3 ./pikaur.py -Syu
```



### Configuração

~ / .config / pikaur.conf


#### [sincronizar]

##### AlwaysShowPkgOrigin (default: no)
Ao instalar novos pacotes, mostre seu nome de repositório mesmo que eles estejam vindo de um dos repositórios oficiais do Arch Linux.

##### DevelPkgsExpiration (default: -1)
Ao fazer o sysupgrade, conte todos os pacotes de devel (-git, -svn, -bzr, -hg, -cvs) com mais de N dias como atualizáveis.
-1 desativa isso.
0 significa sempre atualizar.
Passar o argumento `--devel` substituirá esta opção por 1.


#### [build]

##### KeepBuildDir (default: no)
não remova o diretório `~ / .cache / pikaur / build / $ {PACKAGE_NAME}` entre as compilações.


#### [cores]

cores de terminal, de 0 a 15

##### Version (padrão: 10)
##### VersionDiffOld (padrão: 11)
##### VersionDiffNew (padrão: 9)


#### [ui]

#### RequireEnterConfirm (padrão: yes)
requer a tecla enter para ser pressionada ao responder perguntas.





### Diretórios

```sh
~ / .cache / pikaur /
── aur_repos / # manter lá aur repos; mostre o diff ao atualizar
    └── last_installed.txt # aur repo hash do último pacote instalado com sucesso
── diretório build / # build (removido após a construção bem-sucedida)
── pkg / # construiu diretório de pacotes
~ / .config / pikaur.conf # arquivo de configuração
```

### PERGUNTAS FREQUENTES

##### Como evitar a importação manual de chaves GPG?

É recomendado controlar as chaves manualmente. No entanto, se você souber o que está fazendo, a opção GPG `keyserver-options auto-key-retrieve` irá importar automaticamente as chaves GPG.


### Contribuindo

#### Traduções

Para começar a trabalhar em um novo idioma, diga "es" (espanhol), adicione-o ao
Variável `Makefile`` LANGS` e execute `make`. Então traduza `locale / es.po` usando
seu editor de PO favorito. Executar `make` toda vez que as strings de código do Python mudarem
ou o `.po` é modificado.

Uma vez feito, não se esqueça de distribuir o novo idioma adicionando-o ao
`PKGBUILD`` package () `.
