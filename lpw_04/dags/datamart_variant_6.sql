DROP VIEW IF EXISTS melbourne_housing_datamart;

CREATE VIEW melbourne_housing_datamart AS
SELECT 
    suburb,
    type,
    rooms,
    price,
    distance_from_cbd
FROM 
    stg_melbourne_housing
WHERE
    price > 0;  -- фильтр на корректные цены

COMMENT ON VIEW melbourne_housing_datamart IS 
'Витрина для анализа рынка недвижимости Мельбурна. Поля для визуализации: suburb, type, rooms, price, distance_from_cbd.';