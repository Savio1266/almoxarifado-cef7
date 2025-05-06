import sqlite3


def adicionar_coluna_local():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Verifica se a coluna 'local' já existe
    cursor.execute("PRAGMA table_info(itens)")
    colunas = [col[1] for col in cursor.fetchall()]

    if "local" not in colunas:
        cursor.execute("ALTER TABLE itens ADD COLUMN local TEXT DEFAULT ''")
        conn.commit()
        print("✅ Coluna 'local' adicionada com sucesso.")
    else:
        print("✅ A coluna 'local' já existe.")

    conn.close()


if __name__ == "__main__":
    adicionar_coluna_local()
