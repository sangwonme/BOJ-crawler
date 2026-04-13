n = 10

a = 1
b = 1
result = 0

for i in range(1, n-1):
    result = b
    b += a
    a = result

print(b)