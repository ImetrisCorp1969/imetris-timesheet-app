from streamlit_authenticator import Hasher

# Edit this list of plain-text passwords as needed (temporary)
PLAINS = ["TempPass123!", "AnotherPass!"]

hashed = Hasher(PLAINS).generate()
for p, h in zip(PLAINS, hashed):
    print(f"{p} -> {h}")
