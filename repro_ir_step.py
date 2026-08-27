import sys
sys.path.insert(0, '.')
from datetime import date, timedelta
import src.investments as inv

TODAY = date(2026, 8, 27)
rates = inv.MarketRates()


def make_pos(ages, amounts, produto="CDB", classe="Renda Fixa"):
    lots = [inv.Lot(application_date=TODAY - timedelta(days=a), amount=v)
            for a, v in zip(ages, amounts)]
    p, g = inv.value_at(lots, indexador=inv.Indexador.CDI, taxa=110.0,
                        rates=rates, target=TODAY)
    bd = inv.taxes_at(lots, indexador=inv.Indexador.CDI, taxa=110.0, rates=rates,
                      target=TODAY, classe=classe, isento=False, produto=produto)
    return inv.Position(
        name="CDB Banco X", classe=classe, produto=produto, instituicao="X",
        indexador=inv.Indexador.CDI, taxa=110.0, isento=False, maturity=None,
        principal=bd.principal, gross_today=bd.gross, net_today=bd.net,
        iof_today=bd.iof, ir_today=bd.ir, lots=lots)


def eff(pos, target):
    return inv.taxes_at(pos.lots, indexador=pos.indexador, taxa=pos.taxa,
                        rates=rates, target=target, classe=pos.classe,
                        isento=pos.isento, produto=pos.produto)


def report(title, ages, amounts):
    print("=" * 78)
    print(title)
    pos = make_pos(ages, amounts)
    for lot in sorted(pos.lots, key=lambda l: l.application_date):
        d = (TODAY - lot.application_date).days
        print(f"   lote {lot.application_date} R$ {lot.amount:>10,.2f}  "
              f"{d:>4} dias  IR do lote hoje = {inv.ir_rate_renda_fixa(d)*100:.1f}%")
    step = inv.next_ir_step(pos, today=TODAY)
    print(f"   next_ir_step -> {step}")
    if step:
        sd, cur, nxt = step
        print(f"   BANNER na UI: 'Sua alíquota de IR cai de {cur*100:.1f}% para "
              f"{nxt*100:.1f}% em {sd.strftime('%d/%m/%Y')} "
              f"(faltam {(sd-TODAY).days} dias)'")
    b0 = eff(pos, TODAY)
    print(f"   alíquota EFETIVA da posição hoje       = {b0.ir_pct*100:.2f}%"
          f"   (IR R$ {b0.ir:,.2f}, líquido R$ {b0.net:,.2f})")
    if step:
        b1 = eff(pos, step[0])
        print(f"   alíquota EFETIVA na data anunciada     = {b1.ir_pct*100:.2f}%"
              f"   (IR R$ {b1.ir:,.2f}, líquido R$ {b1.net:,.2f})")
    # varredura dia a dia: quando a alíquota efetiva realmente cai de degrau?
    prev = None
    drops = []
    for i in range(0, 400):
        d = TODAY + timedelta(days=i)
        # alíquota efetiva "congelando" o valor bruto de hoje, para isolar
        # o efeito do degrau (sem o crescimento do rendimento)
        ir_sum = sum(lot.amount * inv.ir_rate_renda_fixa((d - lot.application_date).days)
                     for lot in pos.lots)
        r = ir_sum / sum(l.amount for l in pos.lots)
        if prev is not None and r < prev - 1e-12:
            drops.append((d, prev, r))
        prev = r
    print("   degraus REAIS da posição (alíquota média ponderada por capital):")
    for d, a, b in drops[:4]:
        print(f"      {d}  ({(d-TODAY).days:>3} dias): {a*100:.2f}% -> {b*100:.2f}%")


report("CASO 1 (o do relato): lote de 800 dias + lote de 30 dias",
       [800, 30], [50_000.0, 50_000.0])
report("CASO 2: lote de 170 dias + lote de 30 dias",
       [170, 30], [90_000.0, 10_000.0])
report("CASO 3 (controle): lote único de 30 dias",
       [30], [50_000.0])

# Caso 2 em dinheiro: comparar resgate na data anunciada vs na data real
print("=" * 78)
print("CASO 2 — impacto em R$ do 'Cenário: Próximo degrau de IR' da tabela")
pos = make_pos([170, 30], [90_000.0, 10_000.0])
step = inv.next_ir_step(pos, today=TODAY)
real_step = TODAY + timedelta(days=11)   # lote de 170d cruza 180d
for label, d in [("hoje", TODAY), ("degrau REAL (lote de 170d)", real_step),
                 ("degrau ANUNCIADO por next_ir_step", step[0])]:
    bd = eff(pos, d)
    print(f"   {label:<36} {d}  IR R$ {bd.ir:>9,.2f}  aliq.ef {bd.ir_pct*100:5.2f}%"
          f"  líquido R$ {bd.net:>12,.2f}")
