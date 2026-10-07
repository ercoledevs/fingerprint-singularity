const app = db.getSiblingDB('singularity');
app.createUser({user: 'singularity', pwd: process.env.MONGO_APP_PASSWORD, roles: [{role: 'readWrite', db: 'singularity'}]});
