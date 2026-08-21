# Repository layer: the only place SQL lives. Takes an AsyncSession, returns
# ORM objects or domain dataclasses. Services (pure) and routers (thin) stay free
# of SQL.