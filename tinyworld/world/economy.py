"""A light economy: prices that move with scarcity, wages (already built), and debts.

- Prices are world rules (``price.<resource>``) recomputed once a day from how
  much of each good there is for the people who need it. Scarcity raises the
  price, a glut lowers it, within bounds.
- A debt is a relation: ``SetRelation(debtor, creditor, kind="owes", value=n,
  note=<item>)``. Lending moves goods and writes the debt; repaying moves goods
  back and lowers it. Nothing is created or destroyed except by the effects.
"""

from tinyworld.core import effects as fx
from tinyworld.core.state import Entity, WorldState

OWES = "owes"
FLOOR, CEILING = 0.4, 4.0
BASE = 1.0


def stock_of(state: WorldState, item: str) -> int:
    return sum(e.inventory.get(item, 0) for e in state.entities.values())


def price_of(state: WorldState, item: str) -> float:
    value = state.rules.get(f"price.{item.split(':')[-1]}")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else BASE


def update_prices(state: WorldState) -> list[fx.SetRule]:
    """New prices for the goods people hold, from stock per head. Only changes are returned."""
    people = max(1, len(state.people()))
    out = []
    for item in sorted(e.id for e in state.entities.values() if e.kind in ("item", "resource")):
        stock = stock_of(state, item)
        if stock == 0 and not any(i == item for e in state.entities.values() for i in e.inventory):
            continue
        per_head = stock / people
        # About two of each per person is "enough"; fewer pushes the price up, more pulls it down.
        factor = max(FLOOR, min(CEILING, 2.0 / max(per_head, 0.25)))
        old = price_of(state, item)
        new = round(old + (BASE * factor - old) * 0.3, 2)
        if abs(new - old) >= 0.05:
            out.append(fx.SetRule(key=f"price.{item.split(':')[-1]}", value=new))
    return out


def owed(state: WorldState, debtor: str, creditor: str) -> int:
    relation = state.relation(debtor, creditor)
    return relation.value if relation is not None and relation.kind == OWES else 0


def debts(state: WorldState) -> list[tuple[str, str, int, str]]:
    """(debtor, creditor, amount, item) for every debt that stands."""
    out = []
    for key, relation in sorted(state.relations.items()):
        if relation.kind == OWES and relation.value > 0:
            debtor, creditor = key.split(">")
            out.append((debtor, creditor, relation.value, relation.note))
    return out


def lend(state: WorldState, lender: Entity, borrower_id: str, item: str, quantity: int) -> tuple[list, str] | str:
    borrower = state.entities.get(borrower_id)
    if borrower is None or borrower.kind != "person" or not borrower.alive:
        return "nobody to lend to"
    if borrower.id == lender.id:
        return "cannot lend to oneself"
    if item not in state.entities or state.entities[item].kind not in ("item", "resource"):
        return "no such thing to lend"
    if lender.inventory.get(item, 0) < quantity or quantity <= 0:
        return f"{lender.name} does not have {quantity} to lend"
    if borrower.location != lender.location:
        return f"{borrower.name} is not here"
    existing = owed(state, borrower.id, lender.id)
    if existing and state.relation(borrower.id, lender.id).note != item:
        return f"{borrower.name} already owes {lender.name} something else"
    total = min(100, existing + quantity)
    name = state.entities[item].name
    return [
        fx.TransferItem(item=item, quantity=quantity, source=lender.id, dest=borrower.id),
        fx.SetRelation(source=borrower.id, dest=lender.id, kind=OWES, value=total, note=item),
    ], f"{lender.name} lends {quantity} {name} to {borrower.name}."


def repay(state: WorldState, debtor: Entity, creditor_id: str, quantity: int) -> tuple[list, str] | str:
    creditor = state.entities.get(creditor_id)
    if creditor is None or creditor.kind != "person":
        return "nobody to repay"
    due = owed(state, debtor.id, creditor.id)
    if not due:
        return f"{debtor.name} owes {creditor.name} nothing"
    item = state.relation(debtor.id, creditor.id).note
    pay = min(quantity, due)
    if pay <= 0 or debtor.inventory.get(item, 0) < pay:
        return f"{debtor.name} does not have {pay} to repay"
    if creditor.location != debtor.location:
        return f"{creditor.name} is not here"
    left = due - pay
    return [
        fx.TransferItem(item=item, quantity=pay, source=debtor.id, dest=creditor.id),
        fx.SetRelation(source=debtor.id, dest=creditor.id, kind=OWES if left else "acquaintance", value=left, note=item if left else ""),
    ], f"{debtor.name} repays {pay} {state.entities[item].name} to {creditor.name}" + (f", {left} still owed." if left else ", and owes nothing now.")
