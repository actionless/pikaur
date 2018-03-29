# pikaur

Auxiliar do AUR com dependências mínimas. Revise todos os PKGBUILDs de uma só vez e, em seguida, construa todos eles com o mínimo de interação do usuário.

Inspirado por `pacaur`,` yaourt` e `yay`.

* [Instalação] (# instalação "")
* [Executar sem instalação] (# run-without-installation "")
* [Config file] (# configuration "")
* [Diretórios] (# diretórios "")



### Instalação

`` `sh
git clone https://aur.archlinux.org/pikaur.git
cd pikaur
makepkg -fsri
`` `


### Executar sem instalação

`` `sh
git clone https://github.com/actionless/pikaur.git
cd pikaur
python3 ./pikaur.py -Ss AUR_PACKAGE_NAME
python3 ./pikaur.py -S AUR_PACKAGE_NAME
python3 ./pikaur.py -Syu
`` `


### Configuração

~ / .config / pikaur.conf



### Diretórios

`` `sh
~ / .cache / pikaur /
Aur── aur_repos / # manter lá aur repos; mostre o diff ao atualizar
Last └── last_installed.txt # aur repo hash do último pacote instalado com sucesso
Build── diretório build / # build (removido após a construção bem-sucedida)
P── pkg / # construiu diretório de pacotes
~ / .config / pikaur.conf # arquivo de configuração
