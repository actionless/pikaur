"let g:ale_linters = { 'python': ['ruff', 'pylsp'], }
let g:ale_linters = { 'python': ['ruff', 'pylsp', 'flake8', 'pylint', 'mypy'], }
let g:ale_python_vulture_options = ' ./maintenance_scripts/vulture_whitelist.py '
autocmd VimEnter * :echo "local vimrc loaded! 😺"
