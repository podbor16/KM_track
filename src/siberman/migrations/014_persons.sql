-- Реестр людей Siberman: кто есть кто за все годы, с тёзками. Спецификация:
-- docs/superpowers/specs/2026-10-18-siberman-hall-ratings-records-design.md §3.
-- Привязка выступления к человеку — по естественному ключу (год, номер, этап), а не по
-- participants.id: загрузка Excel удаляет и заново вставляет участников года.
CREATE TABLE IF NOT EXISTS siberman_persons (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  surname         VARCHAR(100) NOT NULL,
  name            VARCHAR(100) NOT NULL DEFAULT '',
  gender          ENUM('M','F') DEFAULT NULL,
  birthdate       DATE DEFAULT NULL,          -- только админка, публично не отдаётся
  bib_individual  VARCHAR(10) DEFAULT NULL,   -- личный номер закреплён за человеком навсегда
  city            VARCHAR(100) NOT NULL DEFAULT '',
  country         VARCHAR(100) NOT NULL DEFAULT '',
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_bib_individual (bib_individual)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- manual=1 — поставлено вручную в админке: синхронизация такие привязки не трогает
-- и не удаляет, даже если строки участника временно нет (перезагрузка года).
-- name_key — ФИ строки на момент привязки: если в перезагруженном протоколе на этом
-- номере и этапе другое ФИ (замена этапника), автопривязка разрешается заново.
CREATE TABLE IF NOT EXISTS siberman_person_links (
  race_year    SMALLINT NOT NULL,
  bib          VARCHAR(10) NOT NULL,
  relay_stage  ENUM('none','swim','bike','run') NOT NULL,
  person_id    INT NOT NULL,
  manual       TINYINT(1) NOT NULL DEFAULT 0,
  name_key     VARCHAR(201) NOT NULL DEFAULT '',
  PRIMARY KEY (race_year, bib, relay_stage),
  KEY idx_person (person_id),
  CONSTRAINT fk_link_person FOREIGN KEY (person_id) REFERENCES siberman_persons(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Из заявок Тильды берём только это: ФИ, пол, ДР, город, номер заявки, дату подачи и
-- сколько стартов на Siberman заявитель указал сам (NULL у этапников эстафеты).
-- Эстафетчики — tranid с суффиксом этапа: '59855:123:swim'.
CREATE TABLE IF NOT EXISTS siberman_applicants (
  tranid          VARCHAR(64) PRIMARY KEY,
  surname         VARCHAR(100) NOT NULL,
  name            VARCHAR(100) NOT NULL DEFAULT '',
  gender          ENUM('M','F') DEFAULT NULL,
  birthdate       DATE NOT NULL,
  city            VARCHAR(100) NOT NULL DEFAULT '',
  submitted_at    DATETIME DEFAULT NULL,
  claimed_starts  SMALLINT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- «Проверить»: выступление (race_year/bib/relay_stage) или человек + кандидаты.
-- dedupe_key не даёт повторной синхронизации плодить одинаковые записи.
CREATE TABLE IF NOT EXISTS siberman_person_reviews (
  id                INT AUTO_INCREMENT PRIMARY KEY,
  kind              VARCHAR(32) NOT NULL,
  dedupe_key        VARCHAR(190) NOT NULL,
  race_year         SMALLINT DEFAULT NULL,
  bib               VARCHAR(10) DEFAULT NULL,
  relay_stage       VARCHAR(5) DEFAULT NULL,
  person_id         INT DEFAULT NULL,
  other_person_ids  VARCHAR(255) NOT NULL DEFAULT '',
  detail            VARCHAR(255) NOT NULL DEFAULT '',
  status            ENUM('open','resolved','deferred') NOT NULL DEFAULT 'open',
  created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at       DATETIME DEFAULT NULL,
  resolved_by       VARCHAR(100) DEFAULT NULL,
  UNIQUE KEY uq_review (dedupe_key),
  CONSTRAINT fk_review_person FOREIGN KEY (person_id) REFERENCES siberman_persons(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Журнал ручных действий: payload — снимок «до» (люди и привязки), scope — что затронуто
-- (вида 'p:12,k:2024/7/none'). Отмена восстанавливает снимок, если позже это не трогали.
CREATE TABLE IF NOT EXISTS siberman_person_audit (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  action      VARCHAR(32) NOT NULL,
  summary     VARCHAR(255) NOT NULL,
  payload     JSON NOT NULL,
  scope       TEXT NOT NULL,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_by  VARCHAR(100) NOT NULL DEFAULT '',
  undone_at   DATETIME DEFAULT NULL,
  undone_by   VARCHAR(100) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
