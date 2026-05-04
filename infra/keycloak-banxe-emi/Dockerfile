FROM quay.io/keycloak/keycloak:26.2.5
ENV KC_DB=postgres
ENV KC_HEALTH_ENABLED=true
ENV KC_METRICS_ENABLED=true
ENV JAVA_OPTS="-Xms256m -Xmx1g -XX:MetaspaceSize=96M -XX:MaxMetaspaceSize=256m -XX:+UseG1GC -Dfile.encoding=UTF-8"
RUN /opt/keycloak/bin/kc.sh build
