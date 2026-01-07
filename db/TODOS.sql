-- =====================================================
-- DATABASE SCHEMA (SOURCE OF TRUTH)
-- Project: Flask + MySQL (PythonAnywhere)
-- =====================================================

-- Kundenkonto (User)
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
) ENGINE=InnoDB;

-- Gesamt-Konto (1:n zu kunden_konto)
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
    FOREIGN KEY (kunden_konto_id)
    REFERENCES kunden_konto(konto_id)
    ON DELETE CASCADE
) ENGINE=InnoDB;

-- Tabelle mit verfügbaren Aktien (fester Preis je Aktie)
CREATE TABLE IF NOT EXISTS available_stocks (
    stock_id   INTEGER PRIMARY KEY,
    name       TEXT,        -- Name oder Kürzel der Aktie
    price      NUMERIC      -- Festgelegter Preis pro Aktie
);
-- Tabelle für den Aktienbestand pro Nutzer 
CREATE TABLE IF NOT EXISTS user_stocks (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER,     -- Referenziert Nutzer (FK auf users.id)
    stock_id   INTEGER,     -- Referenziert Aktie (FK auf available_stocks.stock_id)
    quantity   INTEGER,     -- Anzahl Aktien dieses Typs, die der Nutzer besitzt
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (stock_id) REFERENCES available_stocks(stock_id)
);

-- Tabelle für Sparkonten (ein Eintrag pro Nutzer)
CREATE TABLE IF NOT EXISTS savings_accounts (
    user_id           INTEGER PRIMARY KEY,   -- entspricht Nutzer, 1-zu-1 Beziehung
    balance           NUMERIC,              -- Aktueller Sparkonto-Saldo
    last_interest_date TEXT,               -- Datum der letzten Zinsgutschrift
    FOREIGN KEY (user_id) REFERENCES users(id)
);
