# One shared TrueForge identity for the whole team

TrueForge only lets a caller list the sessions it created, so a distiller can't read other people's sessions under per-user login. For the hackathon, the whole team runs against one no-auth TrueForge instance and each session records its teammate in session metadata. In production this would be replaced by teammates opting in to upload or share their sessions.
