#!/usr/bin/env bash
# SkillSprint AI — Render build script
# يُشغَّل هذا الملف مرةً عند كل نشر (deploy) على Render.
# يقوم بـ:
#   1. تثبيت الحزم
#   2. تشغيل seed إذا لم تكن قاعدة البيانات تحتوي على بيانات

set -e   # أوقف عند أي خطأ

echo "=============================="
echo "  SkillSprint AI — Build Step"
echo "=============================="

# 1. تثبيت المتطلبات
echo "[1/2] Installing Python dependencies..."
pip install --upgrade --no-cache-dir pip
pip install --no-cache-dir -r requirements.txt

# 2. تشغيل seed (آمن — لا يُعيد إدراج البيانات الموجودة)
echo "[2/2] Running database seed (idempotent)..."
python -m database.seed_render

echo "=============================="
echo "  Build complete — starting app"
echo "=============================="
