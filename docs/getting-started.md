# Instalação e primeiro uso

O Git Insights Dashboard é uma aplicação Python com Streamlit que consulta repositórios Git locais sem modificar seus arquivos de trabalho.

## Requisitos

- Python 3.11 ou superior.
- Git disponível no PATH.
- GitHub CLI (gh) opcional, necessário para descobrir repositórios da conta e consultar Pull Requests.
- Acesso ao índice de pacotes Python para instalar as dependências na primeira execução.

## Windows

~~~powershell
git clone https://github.com/ginmp8/git-insights-dashboard.git
cd git-insights-dashboard
.\start-windows.cmd
~~~

Alternativamente, use start-windows.ps1 no PowerShell. A instalação manual:

~~~powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
~~~

## Linux e macOS

~~~sh
git clone https://github.com/ginmp8/git-insights-dashboard.git
cd git-insights-dashboard
./start-linux-macos.sh
~~~

Abra http://127.0.0.1:8501. O servidor é configurado para uso no próprio computador, sem autenticação de usuários. Não o exponha publicamente.

## Criar o primeiro projeto

1. Na barra lateral, crie um projeto.
2. Adicione uma pasta Git local ou escolha a integração GitHub CLI.
3. Para usar a integração, faça gh auth login no terminal uma vez e consulte [Projetos e repositórios](features/projects-and-repositories.md).
4. Selecione repositórios, branches, período, autores e pasta. As abas de relatórios compartilham os filtros do projeto.

## Repositórios de demonstração

Depois de criar o ambiente Python, execute:

~~~powershell
.\.venv\Scripts\python.exe scripts\create_demo.py
~~~

O comando cria três repositórios sintéticos e um projeto de demonstração dentro do armazenamento da aplicação.

## Verificações para desenvolvedores

~~~sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app.py gitinsights scripts tests
~~~

Consulte [VALIDATION.md](../VALIDATION.md) para distinguir testes executados de verificações de interface e autenticação ainda não executadas.

## Atualização do código

Preserve .git-insights-data/ ou configure GIT_INSIGHTS_HOME para apontar para o armazenamento existente. Não apague os espelhos Git durante o upgrade. Veja o [histórico de versões](../releases/README.md).
