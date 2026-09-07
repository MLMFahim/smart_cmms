import os
import csv
import io
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, render_template, Response
from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler
from sqlalchemy.exc import SQLAlchemyError
from waitress import serve

app = Flask(__name__)

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smart_cmms.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Scheduler Configuration
app.config['SCHEDULER_API_ENABLED'] = True

db = SQLAlchemy(app)
scheduler = APScheduler()

# ----------------------------------------------------
# DATABASE MODELS
# ----------------------------------------------------

class Asset(db.Model):
    __tablename__ = 'assets'
    id = db.Column(db.Integer, primary_key=True)
    asset_code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    manufacturer = db.Column(db.String(100), default="N/A")
    model_number = db.Column(db.String(100), default="N/A")
    serial_number = db.Column(db.String(100), default="N/A")
    location_facility = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100), default="General")
    installation_date = db.Column(db.String(20), default="N/A")
    purchase_cost = db.Column(db.Float, default=0.0)
    warranty_expiration = db.Column(db.String(20), default="N/A")
    operational_status = db.Column(db.String(50), default="Operational")
    criticality = db.Column(db.String(20), default="Medium")
    power_rating = db.Column(db.String(50), default="N/A")
    operating_voltage = db.Column(db.String(50), default="N/A")
    maintenance_interval_days = db.Column(db.Integer, default=30)
    last_maintenance_date = db.Column(db.String(20), default="N/A")
    supplier_contact = db.Column(db.String(100), default="N/A")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class SparePart(db.Model):
    __tablename__ = 'spare_parts'
    
    id = db.Column(db.Integer, primary_key=True)
    part_number = db.Column(db.String(50), unique=True, nullable=False)
    part_name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), default="General")
    manufacturer = db.Column(db.String(100), default="N/A")
    model_compatibility = db.Column(db.String(100), default="Universal")
    quantity = db.Column(db.Integer, default=0)
    reorder_threshold = db.Column(db.Integer, default=5)
    reorder_quantity = db.Column(db.Integer, default=10)
    maximum_stock_level = db.Column(db.Integer, default=100)
    unit_of_measure = db.Column(db.String(20), default="PCS")
    unit_cost = db.Column(db.Float, default=0.0)
    storage_bin_location = db.Column(db.String(50), default="A-01")
    warehouse_zone = db.Column(db.String(50), default="Zone A")
    shelf_number = db.Column(db.String(50), default="Shelf 1")
    supplier_name = db.Column(db.String(100), default="N/A")
    supplier_part_no = db.Column(db.String(50), default="N/A")
    lead_time_days = db.Column(db.Integer, default=7)
    criticality_rating = db.Column(db.String(20), default="Medium")
    last_restock_date = db.Column(db.String(20), default="N/A")

    def to_dict(self):
        res = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        res["low_stock"] = (self.quantity or 0) <= (self.reorder_threshold or 0)
        return res


class WorkOrder(db.Model):
    __tablename__ = 'work_orders'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    technician = db.Column(db.String(100), default="Unassigned")
    status = db.Column(db.String(50), default="Pending")
    order_type = db.Column(db.String(50), default="Corrective")
    
    # Financial fields added for Weeks 9 & 10
    labor_hours = db.Column(db.Float, default=0.0)
    hourly_rate = db.Column(db.Float, default=25.0)
    completion_date = db.Column(db.String(20), default="N/A")

    asset = db.relationship('Asset', backref='work_orders')
    parts_used = db.relationship('WorkOrderPart', backref='work_order', cascade="all, delete-orphan")

    def calculate_parts_cost(self):
        total = 0.0
        for item in self.parts_used:
            if item.part:
                total += item.quantity_used * (item.part.unit_cost or 0.0)
        return total

    def calculate_total_cost(self):
        labor_cost = (self.labor_hours or 0.0) * (self.hourly_rate or 0.0)
        return labor_cost + self.calculate_parts_cost()

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "asset_id": self.asset_id,
            "asset_name": self.asset.name if self.asset else "Unknown",
            "technician": self.technician,
            "status": self.status,
            "order_type": self.order_type,
            "labor_hours": self.labor_hours,
            "hourly_rate": self.hourly_rate,
            "parts_cost": self.calculate_parts_cost(),
            "total_cost": self.calculate_total_cost(),
            "completion_date": self.completion_date,
            "parts_used": [
                {"part_id": p.part_id, "part_name": p.part.part_name if p.part else "Unknown", "quantity_used": p.quantity_used}
                for p in self.parts_used
            ]
        }


class WorkOrderPart(db.Model):
    __tablename__ = 'work_order_parts'
    id = db.Column(db.Integer, primary_key=True)
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_orders.id'), nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey('spare_parts.id'), nullable=False)
    quantity_used = db.Column(db.Integer, default=1)

    part = db.relationship('SparePart')


class PreventiveSchedule(db.Model):
    __tablename__ = 'preventive_schedules'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    frequency_days = db.Column(db.Integer, default=30)
    last_generated_date = db.Column(db.String(20), default="N/A")
    next_due_date = db.Column(db.String(20), nullable=False)
    assigned_technician = db.Column(db.String(100), default="Unassigned")
    is_active = db.Column(db.Boolean, default=True)

    asset = db.relationship('Asset', backref='pm_schedules')

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "asset_id": self.asset_id,
            "asset_name": self.asset.name if self.asset else "Unknown",
            "frequency_days": self.frequency_days,
            "last_generated_date": self.last_generated_date,
            "next_due_date": self.next_due_date,
            "assigned_technician": self.assigned_technician,
            "is_active": self.is_active
        }

# ----------------------------------------------------
# AUTOMATED SCHEDULER TASK
# ----------------------------------------------------

def check_and_generate_pm_work_orders():
    with app.app_context():
        today_str = datetime.now().strftime('%Y-%m-%d')
        schedules = db.session.scalars(
            db.select(PreventiveSchedule).where(
                PreventiveSchedule.is_active == True,
                PreventiveSchedule.next_due_date <= today_str
            )
        ).all()

        for pm in schedules:
            new_wo = WorkOrder(
                title=f"[PM Auto] {pm.title}",
                asset_id=pm.asset_id,
                technician=pm.assigned_technician,
                status="In Progress",
                order_type="Preventive"
            )
            db.session.add(new_wo)

            next_date = datetime.now() + timedelta(days=pm.frequency_days)
            pm.last_generated_date = today_str
            pm.next_due_date = next_date.strftime('%Y-%m-%d')

        db.session.commit()

# ----------------------------------------------------
# ROUTES & REST API ENDPOINTS
# ----------------------------------------------------

@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/inventory')
def inventory_page():
    return render_template('inventory.html')

@app.route('/schedules')
def schedules_page():
    return render_template('pm_schedules.html')

@app.route('/reports')
def reports_page():
    return render_template('reports.html')

@app.route('/api/assets', methods=['GET', 'POST'])
def handle_assets():
    if request.method == 'POST':
        try:
            data = request.json or {}
            if 'purchase_cost' in data and data['purchase_cost']:
                data['purchase_cost'] = float(data['purchase_cost'])
            if 'maintenance_interval_days' in data and data['maintenance_interval_days']:
                data['maintenance_interval_days'] = int(data['maintenance_interval_days'])

            asset = Asset(**data)
            db.session.add(asset)
            db.session.commit()
            return jsonify(asset.to_dict()), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

    assets = db.session.scalars(db.select(Asset)).all()
    return jsonify([a.to_dict() for a in assets])

@app.route('/api/parts', methods=['GET', 'POST'])
def handle_parts():
    if request.method == 'POST':
        try:
            data = request.json or {}
            for field in ['quantity', 'reorder_threshold', 'reorder_quantity', 'maximum_stock_level', 'lead_time_days']:
                if field in data and data[field] != '':
                    data[field] = int(data[field])
            if 'unit_cost' in data and data['unit_cost'] != '':
                data['unit_cost'] = float(data['unit_cost'])

            part = SparePart(**data)
            db.session.add(part)
            db.session.commit()
            return jsonify(part.to_dict()), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

    parts = db.session.scalars(db.select(SparePart)).all()
    return jsonify([p.to_dict() for p in parts])

@app.route('/api/parts/low_stock', methods=['GET'])
def get_low_stock():
    parts = db.session.scalars(
        db.select(SparePart).where(SparePart.quantity <= SparePart.reorder_threshold)
    ).all()
    return jsonify([p.to_dict() for p in parts])

@app.route('/api/work_orders', methods=['GET', 'POST'])
def handle_work_orders():
    if request.method == 'POST':
        try:
            data = request.json or {}
            order = WorkOrder(
                title=data['title'], 
                asset_id=int(data['asset_id']), 
                technician=data.get('technician', 'Unassigned'), 
                status="In Progress",
                order_type=data.get('order_type', 'Corrective'),
                labor_hours=float(data.get('labor_hours', 0.0)),
                hourly_rate=float(data.get('hourly_rate', 25.0))
            )
            db.session.add(order)
            db.session.commit()
            return jsonify(order.to_dict()), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

    orders = db.session.scalars(db.select(WorkOrder)).all()
    return jsonify([o.to_dict() for o in orders])

@app.route('/api/work_orders/<int:order_id>/add_part', methods=['POST'])
def add_part_to_work_order(order_id):
    order = db.session.get(WorkOrder, order_id)
    if not order:
        return jsonify({"error": "Work order not found"}), 404

    data = request.json or {}
    part_id = data.get('part_id')
    quantity_used = int(data.get('quantity_used', 1))

    part = db.session.get(SparePart, part_id)
    if not part:
        return jsonify({"error": "Spare part not found"}), 404

    try:
        wo_part = WorkOrderPart(
            work_order_id=order.id,
            part_id=part.id,
            quantity_used=quantity_used
        )
        db.session.add(wo_part)
        db.session.commit()
        return jsonify(order.to_dict())
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/work_orders/<int:order_id>/complete', methods=['POST'])
def complete_work_order(order_id):
    order = db.session.get(WorkOrder, order_id)
    if not order or order.status == 'Completed':
        return jsonify({"error": "Invalid order status or already completed"}), 400

    data = request.get_json(silent=True) or {}
    if 'labor_hours' in data:
        order.labor_hours = float(data['labor_hours'])
    if 'hourly_rate' in data:
        order.hourly_rate = float(data['hourly_rate'])

    try:
        for item in order.parts_used:
            if item.part and item.part.quantity < item.quantity_used:
                return jsonify({
                    "error": f"Insufficient stock for '{item.part.part_name}'. Available: {item.part.quantity}, Needed: {item.quantity_used}"
                }), 400

        for item in order.parts_used:
            if item.part:
                item.part.quantity -= item.quantity_used

        order.status = 'Completed'
        order.completion_date = datetime.now().strftime('%Y-%m-%d')
        
        if order.asset:
            order.asset.last_maintenance_date = order.completion_date

        db.session.commit()
        return jsonify(order.to_dict())
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"error": "Database Error", "details": str(e)}), 500

@app.route('/api/pm_schedules', methods=['GET', 'POST'])
def handle_pm_schedules():
    if request.method == 'POST':
        try:
            data = request.json or {}
            freq = int(data.get('frequency_days', 30))
            
            next_due = datetime.now() + timedelta(days=freq)
            if 'next_due_date' in data and data['next_due_date']:
                next_due_str = data['next_due_date']
            else:
                next_due_str = next_due.strftime('%Y-%m-%d')

            schedule = PreventiveSchedule(
                title=data['title'],
                asset_id=int(data['asset_id']),
                frequency_days=freq,
                next_due_date=next_due_str,
                assigned_technician=data.get('assigned_technician', 'Unassigned')
            )
            db.session.add(schedule)
            db.session.commit()
            return jsonify(schedule.to_dict()), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

    schedules = db.session.scalars(db.select(PreventiveSchedule)).all()
    return jsonify([s.to_dict() for s in schedules])

@app.route('/api/pm_schedules/trigger', methods=['POST'])
def trigger_pm_checks():
    check_and_generate_pm_work_orders()
    return jsonify({"message": "PM generation check executed successfully."})

@app.route('/api/reports/maintenance_costs', methods=['GET'])
def get_cost_report():
    completed_orders = db.session.scalars(
        db.select(WorkOrder).where(WorkOrder.status == 'Completed')
    ).all()

    total_maintenance_cost = sum(o.calculate_total_cost() for o in completed_orders)
    total_parts_cost = sum(o.calculate_parts_cost() for o in completed_orders)
    total_labor_cost = sum((o.labor_hours or 0.0) * (o.hourly_rate or 0.0) for o in completed_orders)

    # Asset cost breakdown
    asset_breakdown = {}
    for o in completed_orders:
        asset_name = o.asset.name if o.asset else "Unknown Asset"
        if asset_name not in asset_breakdown:
            asset_breakdown[asset_name] = 0.0
        asset_breakdown[asset_name] += o.calculate_total_cost()

    return jsonify({
        "total_maintenance_cost": round(total_maintenance_cost, 2),
        "total_parts_cost": round(total_parts_cost, 2),
        "total_labor_cost": round(total_labor_cost, 2),
        "completed_orders_count": len(completed_orders),
        "asset_cost_breakdown": asset_breakdown
    })

@app.route('/api/reports/export/csv', methods=['GET'])
def export_work_orders_csv():
    output = io.StringIO()
    writer = csv.writer(output)

    # CSV Header
    writer.writerow([
        'Work Order ID', 'Title', 'Asset Name', 'Order Type', 
        'Status', 'Technician', 'Labor Hours', 'Hourly Rate ($)', 
        'Parts Cost ($)', 'Total Cost ($)', 'Completion Date'
    ])

    orders = db.session.scalars(db.select(WorkOrder)).all()
    for o in orders:
        writer.writerow([
            o.id,
            o.title,
            o.asset.name if o.asset else "Unknown",
            o.order_type,
            o.status,
            o.technician,
            o.labor_hours,
            o.hourly_rate,
            round(o.calculate_parts_cost(), 2),
            round(o.calculate_total_cost(), 2),
            o.completion_date
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=work_orders_report.csv"}
    )

@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    total_assets = db.session.query(Asset).count()
    total_orders = db.session.query(WorkOrder).count()
    completed_orders = db.session.query(WorkOrder).filter(WorkOrder.status == 'Completed').count()
    in_progress_orders = db.session.query(WorkOrder).filter(WorkOrder.status == 'In Progress').count()
    active_pms = db.session.query(PreventiveSchedule).filter(PreventiveSchedule.is_active == True).count()
    
    all_parts = db.session.scalars(db.select(SparePart)).all()
    low_stock_count = sum(1 for p in all_parts if (p.quantity or 0) <= (p.reorder_threshold or 0))

    return jsonify({
        "total_assets": total_assets,
        "total_work_orders": total_orders,
        "completed_work_orders": completed_orders,
        "in_progress_work_orders": in_progress_orders,
        "low_stock_parts_count": low_stock_count,
        "active_pm_schedules": active_pms
    })

# ----------------------------------------------------
# APPLICATION INITIALIZATION
# ----------------------------------------------------

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    scheduler.add_job(
        id='pm_scheduler_job', 
        func=check_and_generate_pm_work_orders, 
        trigger='interval', 
        hours=24
    )
    scheduler.init_app(app)
    scheduler.start()

    serve(app, host='127.0.0.1', port=5000)