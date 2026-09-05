import os
from flask import Flask, jsonify, request, render_template
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# Local SQLite configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smart_cmms.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ----------------------------------------------------
# DATABASE MODELS
# ----------------------------------------------------

class Asset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), default="Operational")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "location": self.location, "status": self.status}

class SparePart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    part_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, default=0)
    reorder_threshold = db.Column(db.Integer, default=5)

    def to_dict(self):
        return {
            "id": self.id, 
            "part_name": self.part_name, 
            "quantity": self.quantity, 
            "reorder_threshold": self.reorder_threshold
        }

class WorkOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    technician = db.Column(db.String(100), default="Unassigned")
    status = db.Column(db.String(50), default="Pending")

    def to_dict(self):
        asset = db.session.get(Asset, self.asset_id)
        asset_name = asset.name if asset else "Unknown Asset"
        return {
            "id": self.id, 
            "title": self.title, 
            "asset_id": self.asset_id,
            "asset_name": asset_name,
            "technician": self.technician,
            "status": self.status
        }

# ----------------------------------------------------
# FRONTEND ROUTE
# ----------------------------------------------------

@app.route('/')
def dashboard():
    return render_template('index.html')

# ----------------------------------------------------
# ASSETS API (FULL CRUD)
# ----------------------------------------------------

@app.route('/api/assets', methods=['GET'])
def get_assets():
    assets = db.session.scalars(db.select(Asset)).all()
    return jsonify([asset.to_dict() for asset in assets])

@app.route('/api/assets', methods=['POST'])
def create_asset():
    data = request.json
    new_asset = Asset(
        name=data['name'], 
        location=data['location'], 
        status=data.get('status', 'Operational')
    )
    db.session.add(new_asset)
    db.session.commit()
    return jsonify({"message": "Asset added", "asset": new_asset.to_dict()}), 201

@app.route('/api/assets/<int:asset_id>', methods=['PUT'])
def update_asset(asset_id):
    asset = db.session.get(Asset, asset_id)
    if not asset:
        return jsonify({"error": "Asset not found"}), 404
    
    data = request.json
    asset.name = data.get('name', asset.name)
    asset.location = data.get('location', asset.location)
    asset.status = data.get('status', asset.status)
    db.session.commit()
    return jsonify({"message": "Asset updated", "asset": asset.to_dict()})

@app.route('/api/assets/<int:asset_id>', methods=['DELETE'])
def delete_asset(asset_id):
    asset = db.session.get(Asset, asset_id)
    if not asset:
        return jsonify({"error": "Asset not found"}), 404
    db.session.delete(asset)
    db.session.commit()
    return jsonify({"message": "Asset deleted successfully"})

# ----------------------------------------------------
# SPARE PARTS API (FULL CRUD)
# ----------------------------------------------------

@app.route('/api/parts', methods=['GET'])
def get_parts():
    parts = db.session.scalars(db.select(SparePart)).all()
    return jsonify([part.to_dict() for part in parts])

@app.route('/api/parts', methods=['POST'])
def create_part():
    data = request.json
    new_part = SparePart(
        part_name=data['part_name'],
        quantity=data.get('quantity', 0),
        reorder_threshold=data.get('reorder_threshold', 5)
    )
    db.session.add(new_part)
    db.session.commit()
    return jsonify({"message": "Part added", "part": new_part.to_dict()}), 201

@app.route('/api/parts/<int:part_id>', methods=['PUT'])
def update_part(part_id):
    part = db.session.get(SparePart, part_id)
    if not part:
        return jsonify({"error": "Part not found"}), 404
    
    data = request.json
    part.part_name = data.get('part_name', part.part_name)
    part.quantity = data.get('quantity', part.quantity)
    part.reorder_threshold = data.get('reorder_threshold', part.reorder_threshold)
    db.session.commit()
    return jsonify({"message": "Stock updated", "part": part.to_dict()})

@app.route('/api/parts/<int:part_id>', methods=['DELETE'])
def delete_part(part_id):
    part = db.session.get(SparePart, part_id)
    if not part:
        return jsonify({"error": "Part not found"}), 404
    db.session.delete(part)
    db.session.commit()
    return jsonify({"message": "Part deleted successfully"})

# ----------------------------------------------------
# WORK ORDERS API (FULL CRUD)
# ----------------------------------------------------

@app.route('/api/work_orders', methods=['GET'])
def get_work_orders():
    orders = db.session.scalars(db.select(WorkOrder)).all()
    return jsonify([order.to_dict() for order in orders])

@app.route('/api/work_orders', methods=['POST'])
def create_work_order():
    data = request.json
    new_order = WorkOrder(
        title=data['title'],
        asset_id=data['asset_id'],
        technician=data.get('technician', 'Unassigned')
    )
    db.session.add(new_order)
    db.session.commit()
    return jsonify({"message": "Work order created", "work_order": new_order.to_dict()}), 201

@app.route('/api/work_orders/<int:order_id>', methods=['PATCH'])
def update_work_order_status(order_id):
    order = db.session.get(WorkOrder, order_id)
    if not order:
        return jsonify({"error": "Work Order not found"}), 404
    
    data = request.json
    if 'status' in data:
        order.status = data['status']
    if 'technician' in data:
        order.technician = data['technician']
    
    db.session.commit()
    return jsonify({"message": "Work Order updated", "work_order": order.to_dict()})

@app.route('/api/work_orders/<int:order_id>', methods=['DELETE'])
def delete_work_order(order_id):
    order = db.session.get(WorkOrder, order_id)
    if not order:
        return jsonify({"error": "Work Order not found"}), 404
    db.session.delete(order)
    db.session.commit()
    return jsonify({"message": "Work Order deleted successfully"})

# ----------------------------------------------------
# APPLICATION LAUNCH & SEEDING
# ----------------------------------------------------

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        if not db.session.scalars(db.select(Asset)).first():
            a1 = Asset(name="Conveyor Motor A1", location="Building B - Line 1")
            a2 = Asset(name="Hydraulic Press H2", location="Building A - Main Floor")
            db.session.add_all([a1, a2])
            db.session.commit()

        if not db.session.scalars(db.select(SparePart)).first():
            p1 = SparePart(part_name="6205 Bearing", quantity=12, reorder_threshold=5)
            p2 = SparePart(part_name="Hydraulic Seal Kit", quantity=2, reorder_threshold=4)
            db.session.add_all([p1, p2])
            db.session.commit()

        if not db.session.scalars(db.select(WorkOrder)).first():
            w1 = WorkOrder(title="Inspect Motor Vibration", asset_id=1, technician="M.L.M. Fahim", status="In Progress")
            db.session.add(w1)
            db.session.commit()

    app.run(debug=True)