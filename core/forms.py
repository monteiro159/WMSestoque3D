from django import forms

class UploadInventarioForm(forms.Form):
    arquivo_excel = forms.FileField(label="Selecione o Excel do Inventário Diário")
    data_do_inventario = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Data de Referência (Do Excel)"
    )