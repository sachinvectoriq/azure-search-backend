import os
import asyncpg
from typing import Optional, Dict, List, Any
from datetime import datetime
from fastapi import HTTPException
from pydantic import BaseModel

# Database configuration
DB_CONFIG = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

async def get_db_connection():
    return await asyncpg.connect(**DB_CONFIG)


async def azai_report(
    start_date: str,
    end_date: str,
    user_name: Optional[str] = None,
    feedback_type: Optional[str] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch AZAI search logs with feedback from database.
    
    Args:
        start_date: Start date in 'YYYY-MM-DD' format
        end_date: End date in 'YYYY-MM-DD' format
        user_name: Optional user name filter
        feedback_type: Optional feedback type filter
    
    Returns:
        Dictionary with paginated results (p1, p2, p3, etc.)
    """
    try:
        # Convert string dates to datetime objects
        from datetime import datetime as dt
        start_date_obj = dt.strptime(start_date, '%Y-%m-%d').date()
        end_date_obj = dt.strptime(end_date, '%Y-%m-%d').date()
        
        # Base query
        base_query = """
        SELECT
            t1.user_name,
            t1.job_title,
            t1.query,
            t1.ai_response,
            t1.citations,
            t1.date_and_time,
            t2.feedback_type,                     
            t2.feedback    
        FROM 
            azaisearch_logging t1
        LEFT JOIN 
            azaisearch_feedback t2
        ON 
            t1.login_session_id = t2.login_session_id
            AND t1.query = t2.query
            AND t1.ai_response = t2.ai_response
        WHERE 
            t1.user_name NOT IN ('{"Sachin Bhusanurmath"}',
                'HardCodedUser', '{"Jain, Anshuman"}', '{"Chanbasava Koti"}', 
                '{"Sachin Bhusanurmath"}', 'Test User', 'Sai Charan Kumbham', 
                'John Doe', 'Solomon Bhaskar', 'Harsh Aneppanavar', 'Sachin Ksr', 
                'Gaston Chan', 'John Doe1', 'Chanbasava Koti', 'Jain, Anshuman',
                'Sachin Bhusanurmath', 'Anonymous', 'Vinayak Inamadar', 'Raqib Rasheed'
            )
            AND t1.date_and_time >= $1 
            AND t1.date_and_time <= $2
        """
        
        # Build dynamic WHERE clauses and parameters
        params = [start_date_obj, end_date_obj]
        param_counter = 3
        
        if user_name:
            base_query += f" AND t1.user_name = ${param_counter}"
            params.append(user_name)
            param_counter += 1
        
        if feedback_type:
            base_query += f" AND t2.feedback_type = ${param_counter}"
            params.append(feedback_type)
            param_counter += 1
        
        # Add ORDER BY clause
        base_query += " ORDER BY t1.date_and_time DESC"
        
        # Connect to database and execute query
        conn = await get_db_connection()
        
        try:
            # Execute query
            rows = await conn.fetch(base_query, *params)
            
            # Convert rows to list of dictionaries
            results = []
            for row in rows:
                result_dict = {
                    'user_name': row['user_name'],
                    'job_title': row['job_title'],
                    'query': row['query'],
                    'ai_response': row['ai_response'],
                    'citations': row['citations'],
                    'date_and_time': row['date_and_time'].isoformat() if isinstance(row['date_and_time'], datetime) else str(row['date_and_time']),
                    'feedback_type': row['feedback_type'],
                    'feedback': row['feedback']
                }
                results.append(result_dict)
            
            # Paginate results into groups of 15
            paginated_results = {}
            page_size = 15
            
            for i in range(0, len(results), page_size):
                page_number = (i // page_size) + 1
                page_key = f"p{page_number}"
                paginated_results[page_key] = results[i:i + page_size]
            
            return paginated_results
        
        finally:
            await conn.close()
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
