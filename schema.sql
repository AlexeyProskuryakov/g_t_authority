drop table if exists entries;

create table entries (
  e_id integer primary key autoincrement,
  email text ,
  t_id int,
  visit date,
  CONSTRAINT uc_PersonID UNIQUE (email,t_id)
);
