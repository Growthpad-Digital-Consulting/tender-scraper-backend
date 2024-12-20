from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, JWTManager, jwt_required, get_jwt_identity
from app.config import get_db_connection
import logging
import datetime

task_manager_bp = Blueprint('task_manager', __name__)



# Route to get all scraping tasks
@task_manager_bp.route('/api/scraping-tasks', methods=['GET'])
@jwt_required()
def get_scraping_tasks():
    current_user = get_jwt_identity()

    logging.info(f"Fetching tasks for user_id: {current_user}")

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT task_id, name, frequency, start_time, end_time, priority, is_enabled, tender_type 
            FROM scheduled_tasks
            WHERE user_id = %s
        """, (current_user,))

        tasks = cur.fetchall()
        task_list = []
        for task in tasks:
            task_dict = {
                "task_id": task[0],
                "name": task[1],
                "frequency": task[2],
                "priority": task[5],
                "is_enabled": task[6],
                "tender_type": task[7],
                "start_time": task[3],
                "end_time": task[4]
            }

            if task_dict["start_time"] is not None:
                task_dict["start_time"] = task_dict["start_time"].isoformat()
            if task_dict["end_time"] is not None:
                task_dict["end_time"] = task_dict["end_time"].isoformat()

            task_list.append(task_dict)

        return jsonify({"tasks": task_list}), 200
    except Exception as e:
        logging.error(f"Error fetching tasks: {str(e)}")
        return jsonify({"msg": "Error fetching tasks."}), 500


# Task ID Along with User ID
def generate_job_id(user_id, task_id):
    return f"user_{user_id}_task_{task_id}"


def schedule_task_scrape(user_id, task_id, job_function, trigger, **trigger_args):
    job_id = generate_job_id(user_id, task_id)

    existing_job = scheduler.get_job(job_id)
    if existing_job:
        logging.info(f"Removing existing job {job_id} before rescheduling.")
        scheduler.remove_job(job_id)

    try:
        scheduler.add_job(job_function, trigger, id=job_id, **trigger_args)
        logging.info('Scheduled job: %s', job_id)
    except Exception as e:
        logging.error("Error scheduling job %s: %s", job_id, str(e))


# Function to log job events
def job_listener(event):
    if event.exception:
        logging.error('Job %s failed: %s', event.job_id, event.exception)
    else:
        logging.info('Job %s completed successfully.', event.job_id)


# Function to log task events
def log_task_event(task_id, user_id, log_message):
    conn = get_db_connection()
    cur = conn.cursor()
    created_at = datetime.now().isoformat()  # Use ISO format/UTC for consistency
    cur.execute("INSERT INTO task_logs (task_id, user_id, log_entry, created_at) VALUES (%s, %s, %s, %s)",
                (task_id, user_id, log_message, created_at))
    conn.commit()

    # Route to clear logs


@task_manager_bp.route('/api/clear-logs/<int:task_id>', methods=['DELETE'])
@jwt_required()
def clear_logs(task_id):
    current_user = get_jwt_identity()
    logging.info(f"User {current_user} is attempting to clear logs for task ID {task_id}.")

    conn = get_db_connection()
    cur = conn.cursor()

    # Check user permissions
    cur.execute("SELECT user_id FROM scheduled_tasks WHERE task_id = %s", (task_id,))
    task = cur.fetchone()

    if task is None:
        logging.warning(f"No task found for task ID {task_id}.")
        return jsonify({"msg": "Task not found."}), 404

    if task[0] != current_user:
        logging.warning(f"User {current_user} is not authorized to clear logs for task ID {task_id}.")
        return jsonify({"msg": "You do not have permission to clear logs for this task."}), 403

    # Log before deleting
    logging.info(f"Deleting logs for task ID {task_id} for user {current_user}.")

    # Delete logs for the specific task
    cur.execute("DELETE FROM task_logs WHERE task_id = %s AND user_id = %s", (task_id, current_user))
    conn.commit()

    logging.info(f"Logs cleared successfully for task ID {task_id}.")
    return jsonify({"msg": "Logs cleared successfully."}), 200


# Route to add a new scheduled task
@task_manager_bp.route('/api/add-task', methods=['POST'])
@jwt_required()
def add_task():
    current_user = get_jwt_identity()
    data = request.get_json()

    name = data.get('name')
    frequency = data.get('frequency', 'Daily')
    priority = data.get('priority', 'Medium')
    tender_type = data.get('tenderType', 'All')  # Handle tender type

    # If start_time and end_time are provided, parse them; otherwise, set defaults according to frequency
    if data.get('startTime') and data.get('endTime'):
        start_time = parser.parse(data.get('startTime'))
        end_time = parser.parse(data.get('endTime'))
    else:
        current_time = datetime.now()
        if frequency == 'Daily':
            start_time = current_time.replace(hour=10, minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(days=1)  # End time is the next day
        elif frequency == 'Weekly':
            start_time = current_time.replace(hour=10, minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(weeks=1)  # End time is one week later
        else:
            return jsonify({"msg": "Frequency must be either 'Daily' or 'Weekly' or specify start and end times."}), 400

    if not name or start_time is None or end_time is None:
        return jsonify({"msg": "Task name, start time, and end time are required."}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO scheduled_tasks (user_id, name, frequency, start_time, end_time, priority, is_enabled, tender_type)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING task_id;
    """, (
        current_user, name, frequency, start_time, end_time, priority, False, tender_type))  # Include tender_type here

    task_id = cur.fetchone()[0]  # Automatically generated task_id
    conn.commit()

    log_task_event(task_id, current_user, f'Task "{name}" added successfully.')

    return jsonify({"msg": "Task added successfully.", "task_id": task_id}), 201


# Route to fetch logs
@task_manager_bp.route('/api/task-logs/<int:task_id>', methods=['GET'])
@jwt_required()
def get_task_logs(task_id):
    current_user = get_jwt_identity()

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT log_entry, created_at FROM task_logs WHERE task_id = %s AND user_id = %s",
                (task_id, current_user))
    logs = cur.fetchall()

    if not logs:
        return jsonify({"msg": "No logs found for this task."}), 404  # Return a 404 if there are no logs

    logs_list = []
    for log in logs:
        logs_list.append({
            "log_entry": log[0],
            "created_at": log[1]  # Add the created_at field to the response
        })

    return jsonify({"logs": logs_list}), 200


# Route to fetch all task logs for the authenticated user
@task_manager_bp.route('/api/all-task-logs', methods=['GET'])
@jwt_required()
def get_all_task_logs():
    current_user = get_jwt_identity()

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Fetch all logs for the current user
        cur.execute("SELECT task_id, log_entry, created_at FROM task_logs WHERE user_id = %s", (current_user,))
        logs = cur.fetchall()

        if not logs:
            return jsonify({"msg": "No logs found for this user."}), 404  # Return a 404 if there are no logs

        logs_list = []
        for log in logs:
            logs_list.append({
                "task_id": log[0],  # Include task_id for reference
                "log_entry": log[1],
                "created_at": log[2]  # Add the created_at field to the response
            })

        return jsonify({"logs": logs_list}), 200

    except Exception as e:
        logging.error("Error fetching logs: %s", str(e))
        return jsonify({"error": "An error occurred while fetching logs."}), 500
    finally:
        cur.close()
        conn.close()



# Route to cancel a scheduled task
@task_manager_bp.route('/api/cancel-task/<int:task_id>', methods=['DELETE'])
@jwt_required()
def cancel_task(task_id):
    current_user = get_jwt_identity()

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM scheduled_tasks WHERE task_id = %s", (task_id,))
    task = cur.fetchone()

    if task is None:
        return jsonify({"msg": "Task not found."}), 404

    if task[0] != current_user:
        return jsonify({"msg": "You do not have permission to cancel this task."}), 403

    job_id = generate_job_id(current_user, task_id)

    # Check if the job exists before trying to remove it
    job = scheduler.get_job(job_id)
    if job:
        try:
            scheduler.remove_job(job_id)
            log_task_event(task_id, current_user, f'Task "{task_id}" canceled successfully.')
        except Exception as e:
            return jsonify({"msg": f"Failed to remove job {job_id}: {str(e)}"}), 500
    else:
        logging.warning(f"Job {job_id} not found in scheduler.")

    cur.execute("DELETE FROM scheduled_tasks WHERE task_id = %s", (task_id,))
    conn.commit()

    return jsonify({"msg": "Task canceled successfully."}), 200


# Route to toggle task status (Enable/Disable)
@task_manager_bp.route('/api/toggle-task-status/<int:task_id>', methods=['PATCH'])
@jwt_required()
def toggle_task_status(task_id):
    current_user = get_jwt_identity()

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id, is_enabled FROM scheduled_tasks WHERE task_id = %s", (task_id,))
    task = cur.fetchone()

    if task is None:
        return jsonify({"msg": "Task not found."}), 404
    if task[0] != current_user:
        return jsonify({"msg": "You do not have permission to toggle this task's status."}), 403

    new_status = not task[1]
    cur.execute("UPDATE scheduled_tasks SET is_enabled = %s WHERE task_id = %s", (new_status, task_id))
    conn.commit()

    status_message = 'enabled' if new_status else 'disabled'
    log_task_event(task_id, current_user, f'Task "{task_id}" has been {status_message} successfully.')

    return jsonify({"msg": f"Task {task_id} {status_message} successfully."}), 200


# Route to edit a scheduled task
@task_manager_bp.route('/api/edit-task/<int:task_id>', methods=['PUT'])
@jwt_required()
def edit_task(task_id):
    current_user = get_jwt_identity()
    data = request.get_json()

    frequency = data.get('frequency', 'Daily')
    priority = data.get('priority', 'Medium')
    task_name = data.get('name')
    tender_type = data.get('tenderType', 'All')  # Handle tender type

    # Check if start and end times are provided, else set defaults based on frequency
    if data.get('startTime') and data.get('endTime'):
        start_time_str = data.get('startTime')
        end_time_str = data.get('endTime')
        try:
            start_time = parser.parse(start_time_str)
            end_time = parser.parse(end_time_str)
        except ValueError:
            return jsonify({"msg": "Invalid date format for start time or end time."}), 400
    else:
        current_time = datetime.now()
        if frequency == 'Daily':
            start_time = current_time.replace(hour=10, minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(days=1)
        elif frequency == 'Weekly':
            start_time = current_time.replace(hour=10, minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(weeks=1)
        else:
            return jsonify({"msg": "Frequency must be either 'Daily' or 'Weekly' or specify start and end times."}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, name, frequency, start_time, end_time, priority, tender_type FROM scheduled_tasks WHERE task_id = %s",
        (task_id,))
    task = cur.fetchone()

    if task is None:
        return jsonify({"msg": "Task not found."}), 404
    if task[0] != current_user:
        return jsonify({"msg": "You do not have permission to edit this task."}), 403

    # Create log entry for previous and new values
    changes = []
    if task_name != task[1]:
        changes.append(f'Task name changed from "{task[1]}" to "{task_name}"')
    if frequency != task[2]:
        changes.append(f'Frequency changed from "{task[2]}" to "{frequency}"')
    if start_time != task[3]:
        changes.append(f'Start time changed from "{task[3]}" to "{start_time}"')
    if end_time != task[4]:
        changes.append(f'End time changed from "{task[4]}" to "{end_time}"')
    if priority != task[5]:
        changes.append(f'Priority changed from "{task[5]}" to "{priority}"')
    if tender_type != task[6]:
        changes.append(f'Tender type changed from "{task[6]}" to "{tender_type}"')

    # Execute the update including the tender_type
    cur.execute("""
        UPDATE scheduled_tasks SET name = %s, frequency = %s, start_time = %s, end_time = %s, priority = %s, tender_type = %s
        WHERE task_id = %s
    """, (task_name, frequency, start_time, end_time, priority, tender_type, task_id))
    conn.commit()

    # Log all the changes
    log_message = ' and '.join(changes) if changes else 'Task updated with no changes.'
    log_task_event(task_id, current_user, log_message)

    return jsonify({"msg": "Task edited successfully."}), 200


# Route to fetch the next scheduled task for the authenticated user
@task_manager_bp.route('/api/next-schedule', methods=['GET'])
@jwt_required()
def get_next_schedule():
    current_user = get_jwt_identity()

    conn = get_db_connection()
    cur = conn.cursor()

    # Fetch the next scheduled task that is enabled
    cur.execute("""
        SELECT start_time 
        FROM scheduled_tasks 
        WHERE user_id = %s AND is_enabled = TRUE 
        ORDER BY start_time ASC 
        LIMIT 1;
    """, (current_user,))

    result = cur.fetchone()

    # If there is a result, return it, otherwise return "N/A"
    if result:
        return jsonify({"next_schedule": result[0]}), 200
    else:
        return jsonify({"next_schedule": "N/A"}), 200
