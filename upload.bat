@echo off
chcp 65001 > nul
echo ==============================
echo   GitHub 자동 업로드 시작
echo ==============================

cd /d %~dp0

git add .

set /p msg="커밋 메시지 입력 (엔터치면 '자동 업데이트'): "
if "%msg%"=="" set msg=자동 업데이트

git commit -m "%msg%"
git push

echo ==============================
echo   ✅ 업로드 완료!
echo ==============================
pause