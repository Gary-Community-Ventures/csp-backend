# from .extensions import db


# # Example User model
# class User(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     clerk_id = db.Column(
#         db.String(255), unique=True, nullable=False, index=True
#     )  # Store Clerk user ID
#     username = db.Column(
#         db.String(80), unique=True, nullable=True
#     )  # Username from Clerk can be optional
#     email = db.Column(db.String(120), unique=True, nullable=False)
#     created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
#     updated_at = db.Column(
#         db.DateTime,
#         default=db.func.current_timestamp(),
#         onupdate=db.func.current_timestamp(),
#     )

#     def __repr__(self):
#         return f"<User {self.username or self.clerk_id}>"

#     def to_dict(self):
#         return {
#             "id": self.id,
#             "clerk_id": self.clerk_id,
#             "username": self.username,
#             "email": self.email,
#             "created_at": self.created_at.isoformat(),
#             "updated_at": self.updated_at.isoformat(),
#         }
