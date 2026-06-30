ש# תיקון בעיית התקדמות דפים

## 🔴 הבעיה שזוהתה

מהלוגים התגלה שהמערכת מקדימה את הדף **מיד כשנגמרות השאלות**, במקום בסוף היום. זה גרם ל:

1. **ריצה כפולה באותה שעה** - scheduler רץ פעמיים
2. **התנהגות לא עקבית** - באותו משתמש:
   - ריצה ראשונה: דף 25 → אין שאלות → מקדם לדף 26 → "אין שאלות היום"
   - ריצה שנייה: דף 26 (כבר התקדם!) → יש שאלות → שולח שאלה

## ✅ הפתרון שיושם

### עקרון הפתרון
**הפרדה מוחלטת בין שליחת שאלות להתקדמות בדפים:**
- שליחת שאלות: בשעות השליחה הרגילות (לפי הגדרת המשתמש)
- התקדמות דפים: **פעם אחת ביום ב-23:55**

### שינויים שבוצעו ב-`scheduler.py`

#### 1. פונקציה חדשה: `advance_all_subscriptions_daily()`
```python
@log_function_entry
def advance_all_subscriptions_daily():
    """
    Run at 23:55 daily to advance all active subscriptions to the next day.
    This ensures daf progression happens once per day, separate from question sending.
    """
```

**מה הפונקציה עושה:**
- עוברת על כל המנויים הפעילים
- מקדימה כל מנוי ב-`dafim_per_day` שלו
- אם הגיע לסוף הטווח - מסיימת את המנוי ושולחת הודעת סיום
- מדפיסה סטטיסטיקה: כמה מנויים התקדמו וכמה הסתיימו

#### 2. שינוי ב-`run_hour()` - הוספת טריגר ל-23:55
```python
# Special case: 23:55 - advance all subscriptions for tomorrow
if hour == 23 and israel_now.minute >= 55:
    if get_live_mode():
        print("🕐 Running daily subscription advancement at 23:55...")
        advance_all_subscriptions_daily()
    return
```

#### 3. הסרת `advance_subscription()` מ-`finish_subscription_day()`
**לפני:**
```python
# 1. Advance to next day FIRST so we can show tomorrow's study correctly
advance_subscription(sub["id"], sub["dafim_per_day"])
```

**אחרי:**
```python
# Note: Daf advancement removed from here - now happens at 23:55 via advance_all_subscriptions_daily()
```

#### 4. הסרת `advance_subscription()` מ-`send_next_question_or_finish()`
**לפני:**
```python
# Advance for tomorrow
advance_subscription(sub["id"], sub["dafim_per_day"])

# Refresh sub data to get updated current_daf
conn = get_conn()
updated_sub = conn.execute(...).fetchone()
```

**אחרי:**
```python
# Note: Daf advancement removed - happens at 23:55 via advance_all_subscriptions_daily()
# Calculate what tomorrow's study will be (current_daf will be advanced at 23:55)
next_start = sub["current_daf"] + sub["dafim_per_day"]
```

## 🎯 יתרונות הפתרון

1. ✅ **הפרדה ברורה** - שליחת שאלות ≠ התקדמות דפים
2. ✅ **לא משפיע על שעה 00:00** - יש מרווח של 5 דקות
3. ✅ **פשוט ליישום** - לא צריך לשנות לוגיקה מורכבת
4. ✅ **עקבי** - כל המנויים מתקדמים באותו זמן
5. ✅ **קל לניפוי באגים** - ברור מתי קורה מה

## 📋 בדיקות שצריך לבצע

### 1. בדיקה בסימולציה
```python
# בדוק שהפונקציה החדשה עובדת
from scheduler import advance_all_subscriptions_daily
advance_all_subscriptions_daily()
```

### 2. בדיקת התזמון
- וודא שה-scheduler רץ ב-23:55
- בדוק שלא רץ פעמיים באותה דקה

### 3. בדיקת תרחישים
- **תרחיש 1**: משתמש עם שאלות בדף הנוכחי
  - צריך לקבל שאלות היום
  - ב-23:55 הדף יתקדם
  - מחר יקבל שאלות מהדף הבא

- **תרחיש 2**: משתמש בלי שאלות בדף הנוכחי
  - צריך לקבל "אין שאלות היום" עם הדף הנוכחי
  - ב-23:55 הדף יתקדם
  - מחר יקבל שאלות מהדף הבא

- **תרחיש 3**: משתמש שמגיע לסוף הטווח
  - ב-23:55 המנוי יסתיים
  - יקבל הודעת סיום

## ⚠️ הערות חשובות

1. **Connection Pool** - הבעיה של "connection pool exhausted" עדיין קיימת ודורשת תיקון נפרד
2. **Duplicate Runs** - אם עדיין יש ריצות כפולות, צריך לבדוק את ה-scheduler configuration
3. **Timezone** - וודא שהשעה 23:55 היא לפי זמן ישראל (UTC+3)

## 📝 קוד לבדיקה מהירה

```python
# בדיקה ידנית של הפונקציה החדשה
from scheduler import advance_all_subscriptions_daily, get_israel_time
from database import get_conn

# בדוק את הזמן הנוכחי
print(f"Current Israel time: {get_israel_time()}")

# בדוק מנויים פעילים לפני
conn = get_conn()
before = conn.execute("SELECT id, current_daf FROM subscriptions WHERE is_active=1").fetchall()
print(f"Before: {len(before)} active subscriptions")
for sub in before[:3]:  # הצג 3 ראשונים
    print(f"  Sub {sub['id']}: daf {sub['current_daf']}")
conn.close()

# הרץ את ההתקדמות
advanced, completed = advance_all_subscriptions_daily()
print(f"\nAdvanced: {advanced}, Completed: {completed}")

# בדוק מנויים פעילים אחרי
conn = get_conn()
after = conn.execute("SELECT id, current_daf FROM subscriptions WHERE is_active=1").fetchall()
print(f"\nAfter: {len(after)} active subscriptions")
for sub in after[:3]:  # הצג 3 ראשונים
    print(f"  Sub {sub['id']}: daf {sub['current_daf']}")
conn.close()
```

## 🔄 תהליך העבודה החדש

### לפני התיקון:
```
09:00 → שליחת שאלה → אין שאלות → מקדם דף → שולח "אין שאלות"
09:00 (שוב) → יש שאלות בדף החדש → שולח שאלה
```

### אחרי התיקון:
```
09:00 → שליחת שאלה → אין שאלות → שולח "אין שאלות" (ללא התקדמות)
23:55 → מקדם את כל הדפים
09:00 (למחרת) → יש שאלות בדף החדש → שולח שאלה
```

---

**תאריך תיקון:** 25/05/2026  
**גרסה:** 1.0  
**סטטוס:** ✅ מיושם, ממתין לבדיקות
