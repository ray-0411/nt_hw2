# game/bag.py
import random

TETROMINOES = ["I","O","T","S","Z","J","L"]

def seven_bag_stream(seed: int):
    rng = random.Random(seed)
    bag = []
    while True:
        bag = TETROMINOES[:]
        rng.shuffle(bag)             # Fisher-Yates by random.shuffle
        for k in bag:
            yield k
