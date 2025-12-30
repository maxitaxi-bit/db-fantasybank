CREATE TABLE IF NOT EXISTS kunden_konto (
  konto_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  vorname VARCHAR(80) NOT NULL,
  nachname VARCHAR(80) NOT NULL,
  email VARCHAR(255) NOT NULL UNIQUE,
  passwort_hash VARCHAR(255) NOT NULL,
  adresse VARCHAR(255),
  geburtsdatum DATE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_login_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS gesamt_konto (
  gesamt_konto_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  kunden_konto_id BIGINT NOT NULL,
  konto_typ VARCHAR(40) NOT NULL,
  iban VARCHAR(34) UNIQUE,
  waehrung CHAR(3) NOT NULL,
  saldo DECIMAL(18,2) NOT NULL DEFAULT 0,
  schluessel_ref VARCHAR(120),
  status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_gesamt_konto_kunde
    FOREIGN KEY (kunden_konto_id) REFERENCES kunden_konto(konto_id)
);


DROP TABLE IF EXISTS todos;

CREATE TABLE todos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  kunden_konto_id BIGINT NOT NULL,
  content VARCHAR(100) NOT NULL,
  due DATETIME NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_todos_kunde
    FOREIGN KEY (kunden_konto_id)
    REFERENCES kunden_konto(konto_id)
    ON DELETE CASCADE
);
