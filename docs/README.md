# Documentação

Este diretório explica as funcionalidades efetivamente presentes no código do Git Insights Dashboard. Para uma visão rápida, consulte o [README principal](../README.md).

## Primeiros passos

- [Instalação e primeiro uso](getting-started.md): dependências, inicialização, projeto de exemplo e execução dos testes.
- [Privacidade e dados locais](privacy-and-security.md): acesso à rede, armazenamento, espelhos privados e limites de segurança.

## Funcionalidades

- [ICE-Git/1: score relativo auditável e reutilizável](features/ice-git.md): diffs por arquivo/commit, componentes e política versionada (não é produtividade objetiva).\n- [Contribuição anual de engenharia (0.3.0)](features/annual-contribution.md): indicadores por desenvolvedor, histórico integral, persistência SQLite e PRs/revisões opcionais.

- [Projetos e repositórios](features/projects-and-repositories.md): cadastro, GitHub CLI, importação em lote e atualização dos espelhos.
- [Dashboard, autores e arquivos](features/analytics-and-contributors.md): métricas, hotspots, filtros e exportação.
- [Branches e comparações](features/branches-and-comparison.md): histórico deduplicado, ahead/behind e diferenças.
- [Mudanças ajustadas](features/change-quality.md): renomeações, movimentações, espaços e heurísticas de identificadores.
- [Pull Requests e GitHub CLI](features/github-integration.md): consultas opcionais e limites da integração.

## Versões

- [Histórico e notas por versão](../releases/README.md)
- [Changelog resumido](../CHANGELOG.md)
- [Evidências da candidata 0.3.0](../VALIDATION-0.3.0.md) · [Evidências da 0.2.0](../VALIDATION.md)

A documentação da 0.3.0 descreve a candidata na branch de desenvolvimento, não uma release com tag publicada. Resultados de testes e declarações de versão devem ser confrontados com o commit/tag efetivamente utilizado.
