# --- BLOCO DA PREVISÃO DE FATURAS ---
        st.subheader("🗓️ Resumo das Próximas Faturas")
        hoje = pd.Timestamp(date.today())
        
        if hoje.day <= 8:
            mes_base = hoje
            status_fatura_atual = "Aberta"
        elif hoje.day <= 15:
            mes_base = hoje
            status_fatura_atual = "Fechada"
        else:
            mes_base = hoje + pd.DateOffset(months=1)
            status_fatura_atual = "Aberta"
            
        lista_6_meses = [(mes_base + pd.DateOffset(months=i)).strftime('%m/%Y') for i in range(6)]
        
        colunas_fatura = st.columns(6)
        for i, mes_str in enumerate(lista_6_meses):
            if not df_cartao.empty:
                total_mes = df_cartao[(df_cartao['Mês da Fatura'] == mes_str) & (df_cartao['Status'] == 'Pendente')]['Valor'].sum()
            else:
                total_mes = 0.0
                
            label = f"Fatura {mes_str}"
            if i == 0: label += f" ({status_fatura_atual})" 
            
            colunas_fatura[i].metric(label=label, value=f"R$ {total_mes:.2f}")

        st.divider()
        # -------------------------------------
