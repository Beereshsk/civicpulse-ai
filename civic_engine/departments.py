"""Transparent category-to-department routing recommendations."""

DEPARTMENTS = {
    "Roads and potholes": "Public Works",
    "Waterlogging and drainage": "Drainage Services",
    "Waste management": "Sanitation",
    "Streetlights and electricity": "Utilities",
    "Water supply": "Water Services",
    "Public safety": "Public Safety",
    "Other": "Civic Services",
}


def recommend_department(category: str) -> dict:
    department = DEPARTMENTS.get(category, DEPARTMENTS["Other"])
    return {"department": department, "reason": f"{department} is the prototype routing match for {category if category in DEPARTMENTS else 'Other'}."}
