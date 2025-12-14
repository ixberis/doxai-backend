# Guía de Entregabilidad de Email — DoxAI

## 1. Registros DNS Requeridos (juvare.mx en Bluehost/cPanel)

### 1.1 SPF (Sender Policy Framework)

Autoriza qué servidores pueden enviar correo en nombre del dominio.

**Tipo:** TXT  
**Host:** `@` o `juvare.mx`  
**Valor:**
```
v=spf1 +a +mx include:bluehost.com ~all
```

> Si usas múltiples proveedores (ej. también SendGrid), combina:
> ```
> v=spf1 +a +mx include:bluehost.com include:sendgrid.net ~all
> ```

---

### 1.2 DKIM (DomainKeys Identified Mail)

Firma criptográfica que verifica que el correo no fue alterado.

**En cPanel (Bluehost):**
1. Accede a **cPanel > Email > Authentication** (o "Email Deliverability")
2. Busca "DKIM" y haz clic en **Enable** o **Manage**
3. cPanel generará automáticamente el registro DKIM
4. Copia el registro TXT generado y agrégalo en DNS

**Registro típico:**
```
Tipo: TXT
Host: default._domainkey.juvare.mx
Valor: v=DKIM1; k=rsa; p=MIIBIjANBgkqh....[clave pública larga]
```

> **Nota:** El selector puede variar (`default`, `mail`, etc.). Usa el que genere tu panel.

---

### 1.3 DMARC (Domain-based Message Authentication)

Política que indica qué hacer con correos que fallen SPF/DKIM.

**Tipo:** TXT  
**Host:** `_dmarc` o `_dmarc.juvare.mx`  
**Valor (modo monitor inicial):**
```
v=DMARC1; p=none; rua=mailto:dmarc-reports@juvare.mx; ruf=mailto:dmarc-forensic@juvare.mx; pct=100
```

**Después de verificar (modo restrictivo):**
```
v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@juvare.mx; pct=100
```

| Campo | Significado |
|-------|-------------|
| `p=none` | Solo monitorear, no rechazar |
| `p=quarantine` | Enviar a spam si falla |
| `p=reject` | Rechazar completamente |
| `rua` | Email para reportes agregados |
| `pct` | % de correos afectados por la política |

---

## 2. Herramientas de Verificación

### 2.1 Verificar SPF
```bash
# Linux/macOS
dig TXT juvare.mx +short

# O usar nslookup
nslookup -type=TXT juvare.mx
```

**Online:**
- https://mxtoolbox.com/spf.aspx
- https://www.mail-tester.com/spf-lookup/juvare.mx

### 2.2 Verificar DKIM
```bash
dig TXT default._domainkey.juvare.mx +short
```

**Online:**
- https://mxtoolbox.com/dkim.aspx (ingresa selector: `default`, dominio: `juvare.mx`)

### 2.3 Verificar DMARC
```bash
dig TXT _dmarc.juvare.mx +short
```

**Online:**
- https://mxtoolbox.com/dmarc.aspx

### 2.4 Test Completo de Email
- **Mail Tester:** https://www.mail-tester.com (envías un correo de prueba, te da score 1-10)
- **Gmail Headers Analyzer:** En Gmail, abre correo > "..." > "Show original" — muestra si SPF/DKIM/DMARC pasaron

---

## 3. Configuración de Producción

### 3.1 FRONTEND_URL

**Problema:** Los correos con `localhost:8080` no son clickeables en producción y afectan reputación.

**Solución en `.env` de producción:**
```env
FRONTEND_URL=https://app.juvare.mx
# O staging:
FRONTEND_URL=https://staging.doxai.juvare.mx
```

### 3.2 Reply-To Corporativo

Agregar en `SMTPEmailSender` para mejor reputación:

```python
# En build_email_message():
msg["Reply-To"] = "soporte@juvare.mx"
```

### 3.3 List-Unsubscribe (Opcional)

Para correos transaccionales frecuentes, mejora reputación:

```python
# En build_email_message() para correos de marketing:
msg["List-Unsubscribe"] = "<mailto:unsubscribe@juvare.mx>, <https://app.juvare.mx/unsubscribe>"
msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
```

> **Nota:** Para correos de activación/reset NO es necesario, pero sí para newsletters.

---

## 4. Outlook/Hotmail: Registro en Postmaster

Si Outlook sigue rechazando:

### 4.1 Microsoft SNDS (Smart Network Data Services)
1. Ve a https://sendersupport.olc.protection.outlook.com/snds/
2. Registra tu IP de envío (la IP de Bluehost SMTP)
3. Solicita acceso para monitorear reputación

### 4.2 Microsoft JMRP (Junk Mail Reporting Program)
- https://postmaster.live.com/snds/JMRP.aspx
- Recibe notificaciones cuando usuarios marcan como spam

### 4.3 Alternativa: Proveedor Transaccional

Para alta entregabilidad en correos críticos (activación, reset), considera:

| Proveedor | Free Tier | Ventajas |
|-----------|-----------|----------|
| **SendGrid** | 100/día | Fácil integración, buena reputación |
| **Mailgun** | 5,000/mes | API robusta, logs detallados |
| **Amazon SES** | 62,000/mes (desde EC2) | Muy barato, requiere más config |
| **Resend** | 3,000/mes | API moderna, React Email support |
| **Postmark** | 100/mes | Excelente entregabilidad transaccional |

---

## 5. Checklist de Entregabilidad

- [ ] SPF configurado y validado
- [ ] DKIM habilitado en cPanel y registro DNS creado
- [ ] DMARC configurado (iniciar con `p=none`)
- [ ] FRONTEND_URL apunta a dominio público (no localhost)
- [ ] From/Reply-To usan dominio verificado
- [ ] Probado con mail-tester.com (score ≥ 8/10)
- [ ] Headers incluyen Date, Message-ID, From, To, Subject
- [ ] Correo es multipart/alternative (text + html)
- [ ] No hay enlaces rotos en el HTML
- [ ] Dominio no está en blacklists (verificar en mxtoolbox.com/blacklists)

---

## 6. Ejemplo de Registros DNS Finales

| Tipo | Host | Valor |
|------|------|-------|
| TXT | `@` | `v=spf1 +a +mx include:bluehost.com ~all` |
| TXT | `default._domainkey` | `v=DKIM1; k=rsa; p=MIIBIjAN...` (generado por cPanel) |
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:dmarc@juvare.mx; pct=100` |

---

## 7. Comandos de Diagnóstico

```bash
# Verificar todos los registros de email
dig MX juvare.mx +short
dig TXT juvare.mx +short
dig TXT _dmarc.juvare.mx +short
dig TXT default._domainkey.juvare.mx +short

# Verificar si IP está en blacklist
# Primero obtén la IP de tu servidor SMTP:
dig A box5201.bluehost.com +short
# Luego verifica en: https://mxtoolbox.com/blacklists.aspx
```

---

*Última actualización: 2025-12-14*
