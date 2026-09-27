from typing import Iterable


def transfer_money(sender, receiver, amount: int) -> bool:
    """Transfer money between two entities.

    Returns False when the sender cannot afford the transaction.
    """

    if amount <= 0:
        raise ValueError("Transfer amount must be positive.")

    if not hasattr(sender, "money"):
        raise TypeError("Sender must have a money attribute.")

    if not hasattr(receiver, "money"):
        raise TypeError("Receiver must have a money attribute.")

    if sender.money < amount:
        return False

    sender.money -= amount
    receiver.money += amount

    return True


def total_money(entities: Iterable) -> int:
    """Return the total money held by all supplied entities."""

    total = 0

    for entity in entities:
        if not hasattr(entity, "money"):
            raise TypeError("Every entity must have a money attribute.")

        total += entity.money

    return total