# pikaur

Auxiliar do AUR com dependências mínimas. Revise todos os PKGBUILDs de uma só vez e, em seguida, construa todos eles com o mínimo de interação do usuário.

Inspirado por `pacaur`,` yaourt` e `yay`.



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



### Diretórios
```sh
~/.cache/pikaur/
├── aur_repos/  # keep there aur repos; show diff when updating
│   └── last_installed.txt  # aur repo hash of last successfully installed package
├── build/  # build directory (removed after successfull build)
└── pkg/  # built packages directory
~/.config/pikaur.conf  # config file
```
