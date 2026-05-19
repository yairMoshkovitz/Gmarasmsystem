# מדריך לוגים מפורטים במצב DEBUG

## סקירה כללית

המערכת כעת מוגדרת עם לוגים מפורטים ברמת DEBUG באופן דיפולטיבי. כל פונקציה שנכנסים אליה תתן לוג אוטומטי עם הפרמטרים שלה.

## מה הוסף למערכת?

### 1. קובץ תצורת לוגים חדש: `logging_config.py`

קובץ זה מכיל:
- **הגדרת רמת לוגים**: DEBUG כברירת מחדל
- **פורמט מפורט**: כולל תאריך, שעה, שם קובץ, מספר שורה, שם פונקציה
- **דקורטור `@log_function_entry`**: מוסיף לוגים אוטומטיים לכניסה ויציאה מפונקציות

### 2. פורמט הלוגים

כל לוג כולל:
```
2026-05-19 23:07:20,617 - QA-SMS.module_name - DEBUG - [file.py:42] - function_name() - Message
```

- **תאריך ושעה מדויקים**
- **שם המודול**
- **רמת הלוג** (DEBUG/INFO/WARNING/ERROR)
- **קובץ ומספר שורה**
- **שם הפונקציה**
- **ההודעה**

### 3. לוגים אוטומטיים לכניסה/יציאה מפונקציות

כאשר פונקציה מסומנת עם `@log_function_entry`:
```python
@log_function_entry
def my_function(param1, param2):
    # קוד הפונקציה
    pass
```

הלוגים יראו כך:
```
→ ENTERING module.my_function(param1='value1', param2='value2')
← EXITING module.my_function() - Success
```

## קבצים שעודכנו

כל הקבצים הבאים עודכנו עם לוגים מפורטים:

1. ✅ **app.py** - כל ה-routes וה-endpoints
2. ✅ **scheduler.py** - כל פונקציות התזמון
3. ✅ **simulation_system.py** - טיפול בהודעות משתמשים
4. ✅ **registration.py** - רישום והרשמות
5. ✅ **sms_service.py** - שליחה וקבלה של SMS
6. ✅ **questions_engine.py** - בחירת שאלות
7. ✅ **state_manager.py** - ניהול מצבי משתמשים
8. ✅ **questions_engine.py** - מנוע השאלות

## איך להשתמש?

### בקוד קיים
הלוגים כבר פעילים! פשוט הרץ את המערכת והלוגים יופיעו אוטומטית.

### בקוד חדש
כדי להוסיף לוגים לפונקציה חדשה:

```python
from logging_config import get_logger, log_function_entry

logger = get_logger(__name__)

@log_function_entry
def my_new_function(param1, param2):
    """תיאור הפונקציה"""
    logger.debug("הודעת debug נוספת")
    logger.info("הודעת מידע")
    logger.warning("אזהרה")
    logger.error("שגיאה")
    
    # קוד הפונקציה...
    return result
```

## בדיקת הלוגים

הרץ את הסקריפט לבדיקה:
```bash
python test_debug_logging.py
```

זה יריץ מספר בדיקות ויציג לוגים מפורטים.

## דוגמאות ללוגים

### כניסה לפונקציה עם פרמטרים:
```
2026-05-19 23:07:20,617 - QA-SMS - DEBUG - [logging_config.py:41] - wrapper() - → ENTERING __main__.test_function_1(3, 7)
```

### יציאה מפונקציה:
```
2026-05-19 23:07:20,618 - QA-SMS - DEBUG - [logging_config.py:45] - wrapper() - ← EXITING __main__.test_function_1() - Success
```

### לוג רגיל בתוך פונקציה:
```
2026-05-19 23:07:20,617 - QA-SMS.__main__ - DEBUG - [test_debug_logging.py:11] - test_function_1() - Inside test_function_1
```

### טיפול בשגיאות:
```
2026-05-19 23:07:20,620 - QA-SMS.__main__ - ERROR - [test_debug_logging.py:38] - test_exception_handling() - Caught expected error: division by zero
```

## יתרונות

1. ✅ **מעקב מלא** - רואים בדיוק איזה פונקציות נקראות ובאיזה סדר
2. ✅ **פרמטרים** - רואים את הערכים שהועברו לכל פונקציה
3. ✅ **זמנים** - יכול לזהות בעיות ביצועים
4. ✅ **מיקום מדויק** - קובץ ושורה מדויקים לכל לוג
5. ✅ **דיבאג קל** - מאוד קל לעקוב אחרי הזרימה של הקוד

## הערות חשובות

- **ביצועים**: במצב ייצור (production) כדאי לשקול להעלות את רמת הלוגים ל-INFO או WARNING
- **גודל קבצים**: לוגים ברמת DEBUG יוצרים הרבה מידע - כדאי להגדיר rotation של קבצי לוג
- **מידע רגיש**: שים לב שלא לתעד מידע רגיש (סיסמאות, מספרי כרטיס אשראי וכו')

## שינוי רמת הלוגים

אם תרצה לשנות את רמת הלוגים, ערוך את `logging_config.py`:

```python
# לשנות מ-DEBUG ל-INFO:
logging.basicConfig(
    level=logging.INFO,  # במקום DEBUG
    ...
)
```

רמות לוגים זמינות:
- `DEBUG` - הכי מפורט (ברירת מחדל כעת)
- `INFO` - מידע כללי
- `WARNING` - אזהרות
- `ERROR` - שגיאות
- `CRITICAL` - שגיאות קריטיות

---

**תאריך יצירה**: 19/05/2026  
**גרסה**: 1.0  
**מטרה**: מעקב עמוק יותר אחרי הקוד לצורכי דיבאג
