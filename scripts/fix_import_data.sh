#!/usr/bin/env bash
# ============================================================
# 修复历史脏数据（2026-08-10 首次Excel导入产生）
# 问题：
#   1. district 被填成景观（园区/海景/园林），真实区域信息缺失
#   2. 出租房源 price 单位错误：Excel 月租(元) 未转万元，显示成"XXX万"
#      （price 列已从 integer 迁移为 numeric(12,2)，支持万元小数 0.13）
#   3. 部分房源 price=0（无价格数据，保留0待补充）
# 前置条件：已执行 ALTER TABLE re_properties ALTER COLUMN price TYPE numeric(12,2)
# 用法：在服务器上执行  bash scripts/fix_import_data.sh
# ============================================================
set -euo pipefail

DB_URL="${DATABASE_URL:-postgresql://hermes:2a8122e1118ce16f747959fa66184a83@localhost:5432/hermes_agent}"

echo "== 0. price 列迁移 integer → numeric(12,2)（支持出租月租万元小数） =="
psql "$DB_URL" -c "ALTER TABLE re_properties ALTER COLUMN price TYPE numeric(12,2) USING price::numeric;"

echo "== 修复前 =="
psql "$DB_URL" -t -c "SELECT property_type, count(*) FROM re_properties WHERE district IN ('园区','海景','园林') GROUP BY property_type;"

echo "== 1. 景观从 district 移到 tags =="
psql "$DB_URL" -c "UPDATE re_properties SET tags = CASE WHEN tags IS NULL OR tags='' THEN '景观:'||district ELSE tags||',景观:'||district END WHERE district IN ('园区','海景','园林');"

echo "== 2. district 置空（无真实区域数据，宁可空不能错） =="
psql "$DB_URL" -c "UPDATE re_properties SET district = '' WHERE district IN ('园区','海景','园林');"

echo "== 3. 出租房源价格 元/月 → 万元（0.1267 = 1267元/月） =="
psql "$DB_URL" -c "UPDATE re_properties SET price = round(price/10000.0, 4) WHERE property_type='rental' AND price > 100;"

echo "== 4. 重算出租 unit_price（元/㎡，按新 price） =="
psql "$DB_URL" -c "UPDATE re_properties SET unit_price = CASE WHEN area > 0 THEN round((price*10000.0/area)::numeric, 0)::int ELSE unit_price END WHERE property_type='rental' AND price > 0;"

echo "== 修复后校验 =="
psql "$DB_URL" -t -c "SELECT property_type, min(price), max(price), round(avg(price),4) FROM re_properties GROUP BY property_type;"
psql "$DB_URL" -t -c "SELECT count(*) AS remaining_wrong_district FROM re_properties WHERE district IN ('园区','海景','园林');"
psql "$DB_URL" -t -c "SELECT count(*) AS total_with_tags FROM re_properties WHERE tags IS NOT NULL AND tags != '';"
echo "== 完成 =="
