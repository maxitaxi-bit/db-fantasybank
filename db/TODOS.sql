-- =====================================================
-- DATABASE SCHEMA (FINAL VERSION)
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
  stock_id INT AUTO_INCREMENT PRIMARY KEY,
  name TEXT NOT NULL,
  price DECIMAL(10,2) NOT NULL
) ENGINE=InnoDB;

-- Aktienbestand pro Nutzer
CREATE TABLE IF NOT EXISTS user_stocks (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  stock_id INT NOT NULL,
  quantity INT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES kunden_konto(konto_id) ON DELETE CASCADE,
  FOREIGN KEY (stock_id) REFERENCES available_stocks(stock_id)
) ENGINE=InnoDB;

-- Sparkonten (1:1 zu Nutzer)
CREATE TABLE IF NOT EXISTS savings_accounts (
  user_id BIGINT PRIMARY KEY,
  balance DECIMAL(18,2) NOT NULL DEFAULT 0,
  last_interest_date DATE,
  FOREIGN KEY (user_id) REFERENCES kunden_konto(konto_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Wechselkurse (feste Rates)
CREATE TABLE IF NOT EXISTS exchange_rates (
  id INT AUTO_INCREMENT PRIMARY KEY,
  from_currency CHAR(3) NOT NULL,
  to_currency CHAR(3) NOT NULL,
  rate DECIMAL(10,4) NOT NULL
) ENGINE=InnoDB;

-- Fremdwährungs-Guthaben pro Nutzer
CREATE TABLE IF NOT EXISTS user_balances (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  currency CHAR(3) NOT NULL,
  balance DECIMAL(18,2) NOT NULL DEFAULT 0,
  UNIQUE(user_id, currency),
  FOREIGN KEY (user_id) REFERENCES kunden_konto(konto_id) ON DELETE CASCADE
) ENGINE=InnoDB;
