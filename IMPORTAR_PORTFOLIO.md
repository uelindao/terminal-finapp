# Como importar seu portfólio no FinTerminal

## Passo 1: Gerar a planilha com IA

Envie os prints da sua corretora para o Claude ou ChatGPT
com o seguinte prompt:

---

> "Analise as imagens da minha corretora e extraia todas as
> posições de ações e FIIs. Gere um arquivo CSV com exatamente
> estas colunas:
>
> ticker,quantidade,preco_medio,notas
>
> Regras:
> - ticker: código da ação (ex: WEGE3.SA para B3, AAPL para EUA)
> - quantidade: número inteiro de cotas/ações
> - preco_medio: preço médio de compra com 2 casas decimais
> - notas: deixe em branco se não houver observação
>
> Retorne APENAS o conteúdo CSV, sem explicações."

---

## Passo 2: Salvar como CSV

Salve o resultado como arquivo `.csv` (ex: `minha_carteira.csv`).

## Passo 3: Importar no terminal

**Portfolio** → aba **Posições** → expander **📥 importar portfólio via planilha** → faça o upload do arquivo gerado.

---

## Formato aceito

| Coluna | Obrigatória | Exemplo |
|---|---|---|
| `ticker` | ✅ | `WEGE3.SA`, `AAPL` |
| `quantidade` | ✅ | `100` |
| `preco_medio` | ✅ | `38.50` ou `38,50` |
| `nome` | ❌ | `WEG S.A.` |
| `notas` | ❌ | `posição principal` |

- Separador: vírgula ou ponto-e-vírgula
- Decimal: ponto ou vírgula
- Tickers B3 sem `.SA` são detectados automaticamente
