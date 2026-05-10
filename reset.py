import sqlite3
import hashlib
import os

# cria a nova segurança
salt = os.urandom(16).hex()
senha_nova = "admin123"
hash_calculado = hashlib.sha256(f"{salt}{senha_nova}".encode()).hexdigest()

# liga ao banco e atualiza
conn = sqlite3.connect('finterminal.db')
conn.execute("UPDATE usuarios SET senha_hash=?, salt=? WHERE username='admin'", (hash_calculado, salt))
conn.commit()
conn.close()

print("✅ senha do admin resetada com sucesso para: admin123")