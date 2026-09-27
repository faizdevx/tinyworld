from WORLD.Clock.clock import Clock


clock=Clock()

for i in range(20):
    print(clock.time_string(),clock.phase)
    clock.tick()