import math
import random
from scipy.stats import norm
import csv

mu = 0.0
sigma = 2.0
k = 1.0
counter = 0.0
iteration = 0

with open('backoff_simulation.csv', mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(['Iteration', 'Counter', 'Wait_Time'])

    while counter <= 100.0:
        iteration += 1
        x = round(random.uniform(-k, k), 8)
        y = 2 * (norm.cdf(math.tan((math.pi / (2 * k)) * x), loc=mu, scale=sigma) - 0.5)
        noise = y
        counter += 0.3 + noise
        wait_time = (1 / 12) * math.sqrt(counter ** 2 + 144)
        writer.writerow([iteration, counter, wait_time])
