import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import catalog


class TestCatalogo(unittest.TestCase):
    def test_ids_unicos(self):
        ids = [i["id"] for i in catalog.ITENS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_campos_validos(self):
        for i in catalog.ITENS:
            self.assertIn(i["tipo"], catalog.TIPOS, i["id"])
            self.assertIn(i["raridade"], catalog.RARIDADES, i["id"])
            self.assertIsInstance(i["preco"], int, i["id"])
            self.assertGreaterEqual(i["preco"], 0, i["id"])
            self.assertTrue(i["nome"] and i["desc"], i["id"])

    def test_padroes_gratis(self):
        for tipo in ("especie", "vaso"):
            p = catalog.padrao(tipo)
            self.assertEqual(p["preco"], 0)
        self.assertEqual(catalog.padrao("especie")["id"], "muda")
        self.assertEqual(catalog.padrao("vaso")["id"], "terracota")
        self.assertIsNone(catalog.padrao("companheiro"))

    def test_faixas_de_preco_do_plano(self):
        faixas = {"vaso": (12, 30), "companheiro": (20, 50), "acessorio": (16, 30), "especie": (40, 120)}
        for i in catalog.ITENS:
            if i["tipo"] in faixas and i["preco"] > 0:
                lo, hi = faixas[i["tipo"]]
                self.assertTrue(lo <= i["preco"] <= hi, (i["id"], i["preco"]))
        self.assertEqual(catalog.item("slot_2")["preco"], 60)
        self.assertEqual(catalog.item("slot_3")["preco"], 110)

    def test_catalogo_soma_bem_mais_que_o_orcamento(self):
        total = sum(i["preco"] for i in catalog.ITENS)
        self.assertGreater(total, 800)

    def test_raridade_sobe_com_o_preco(self):
        ordem = {r: n for n, r in enumerate(catalog.RARIDADES)}
        for tipo in catalog.FAIXAS_RARIDADE:
            venda = [i for i in catalog.itens_por_tipo(tipo) if not i.get("exclusivo")]
            for a in venda:
                for b in venda:
                    if a["preco"] > b["preco"]:
                        self.assertGreaterEqual(ordem[a["raridade"]], ordem[b["raridade"]], (a["id"], b["id"]))
                    if a["preco"] == b["preco"]:
                        self.assertEqual(a["raridade"], b["raridade"], (a["id"], b["id"]))

    def test_mais_caras_de_cada_tipo(self):
        self.assertEqual(catalog.item("ipe")["raridade"], "lendaria")
        self.assertEqual(catalog.item("baoba")["raridade"], "lendaria")
        self.assertEqual(catalog.item("bonsai")["raridade"], "epica")
        self.assertEqual(catalog.item("dourado")["raridade"], "epica")
        self.assertEqual(catalog.item("muda")["raridade"], "comum")
        self.assertEqual(catalog.item("selo_fundador")["raridade"], "lendaria")

    def test_nome_da_raridade_com_acento(self):
        self.assertEqual(catalog.item("ipe")["raridade_nome"], "Lendária")
        self.assertEqual(catalog.item("carnivora")["raridade_nome"], "Épica")

    def test_item_inexistente(self):
        self.assertIsNone(catalog.item("nao-existe"))


class TestCompra(unittest.TestCase):
    def test_compra_simples(self):
        ok, _ = catalog.pode_comprar("girassol", saldo=40, possui=set(), floresceu=False)
        self.assertTrue(ok)

    def test_saldo_insuficiente(self):
        ok, motivo = catalog.pode_comprar("girassol", saldo=39, possui=set(), floresceu=False)
        self.assertFalse(ok)
        self.assertIn("semente", motivo)

    def test_ja_possui(self):
        ok, _ = catalog.pode_comprar("girassol", saldo=199, possui={"girassol"}, floresceu=False)
        self.assertFalse(ok)

    def test_padrao_nao_se_compra(self):
        ok, _ = catalog.pode_comprar("muda", saldo=199, possui=set(), floresceu=False)
        self.assertFalse(ok)

    def test_baoba_exige_ter_florescido(self):
        ok, motivo = catalog.pode_comprar("baoba", saldo=199, possui=set(), floresceu=False)
        self.assertFalse(ok)
        self.assertIn("flor", motivo.lower())
        ok, _ = catalog.pode_comprar("baoba", saldo=199, possui=set(), floresceu=True)
        self.assertTrue(ok)

    def test_slot_3_exige_slot_2(self):
        ok, _ = catalog.pode_comprar("slot_3", saldo=199, possui=set(), floresceu=False)
        self.assertFalse(ok)
        ok, _ = catalog.pode_comprar("slot_3", saldo=199, possui={"slot_2"}, floresceu=False)
        self.assertTrue(ok)

    def test_item_desconhecido(self):
        ok, _ = catalog.pode_comprar("fantasma", saldo=199, possui=set(), floresceu=False)
        self.assertFalse(ok)


class TestEquipar(unittest.TestCase):
    def test_equipar_item_comprado(self):
        ok, _ = catalog.pode_equipar("girassol", "especie", possui={"girassol"})
        self.assertTrue(ok)

    def test_nao_equipa_o_que_nao_tem(self):
        ok, _ = catalog.pode_equipar("girassol", "especie", possui=set())
        self.assertFalse(ok)

    def test_padrao_sempre_pode(self):
        ok, _ = catalog.pode_equipar("muda", "especie", possui=set())
        self.assertTrue(ok)
        ok, _ = catalog.pode_equipar("terracota", "vaso", possui=set())
        self.assertTrue(ok)

    def test_tipo_errado_no_slot(self):
        ok, _ = catalog.pode_equipar("azul", "especie", possui={"azul"})
        self.assertFalse(ok)

    def test_segunda_planta_exige_slot_2(self):
        ok, _ = catalog.pode_equipar("girassol", "especie_2", possui={"girassol"})
        self.assertFalse(ok)
        ok, _ = catalog.pode_equipar("girassol", "especie_2", possui={"girassol", "slot_2"})
        self.assertTrue(ok)

    def test_terceira_planta_exige_slot_3(self):
        ok, _ = catalog.pode_equipar("muda", "especie_3", possui={"slot_2"})
        self.assertFalse(ok)
        ok, _ = catalog.pode_equipar("muda", "especie_3", possui={"slot_2", "slot_3"})
        self.assertTrue(ok)

    def test_slot_desconhecido(self):
        ok, _ = catalog.pode_equipar("muda", "chapeu", possui=set())
        self.assertFalse(ok)

    def test_slot_nao_e_equipavel(self):
        ok, _ = catalog.pode_equipar("slot_2", "especie", possui={"slot_2"})
        self.assertFalse(ok)


class TestMontarVisual(unittest.TestCase):
    def test_padroes(self):
        v = catalog.montar_visual(set(), {})
        self.assertEqual(v["especie"], "muda")
        self.assertEqual(v["vaso"], "terracota")
        self.assertIsNone(v["companheiro"])
        self.assertIsNone(v["acessorio"])
        self.assertEqual(v["extras"], [])
        self.assertEqual(v["folha"], "p-folha")

    def test_equipados_validos(self):
        v = catalog.montar_visual({"samambaia", "azul", "gato", "oculos"},
                                  {"especie": "samambaia", "vaso": "azul",
                                   "companheiro": "gato", "acessorio": "oculos"})
        self.assertEqual(v["especie"], "samambaia")
        self.assertEqual(v["folha"], "p-folha-fina")
        self.assertEqual(v["vaso"], "azul")
        self.assertEqual(v["companheiro"], "gato")
        self.assertEqual(v["acessorio"], "oculos")

    def test_item_que_nao_e_mais_dele_e_ignorado(self):
        v = catalog.montar_visual(set(), {"especie": "girassol", "companheiro": "gato"})
        self.assertEqual(v["especie"], "muda")
        self.assertIsNone(v["companheiro"])

    def test_extras_exigem_slot_comprado(self):
        v = catalog.montar_visual({"girassol"}, {"especie_2": "girassol"})
        self.assertEqual(v["extras"], [])
        v = catalog.montar_visual({"girassol", "slot_2"}, {"especie_2": "girassol"})
        self.assertEqual([e["especie"] for e in v["extras"]], ["girassol"])
        self.assertEqual(v["extras"][0]["slot"], 2)

    def test_extra_sem_escolha_usa_muda(self):
        v = catalog.montar_visual({"slot_2", "slot_3"}, {})
        self.assertEqual([e["especie"] for e in v["extras"]], ["muda", "muda"])
        self.assertEqual([e["slot"] for e in v["extras"]], [2, 3])

    def test_colecao_tem_as_especies_compradas_fora_de_uso(self):
        self.assertEqual(catalog.montar_visual(set(), {})["colecao"], [])
        v = catalog.montar_visual({"girassol", "cacto", "lavanda", "slot_2", "gato"},
                                  {"especie": "cacto", "especie_2": "girassol"})
        # cacto esta no vaso, girassol na extra: so a lavanda cresce solta; companheiro nao entra
        self.assertEqual([e["especie"] for e in v["colecao"]], ["lavanda"])
        self.assertEqual(v["colecao"][0]["folha"], catalog._folha("lavanda"))


class TestFundador(unittest.TestCase):
    """Fase 1.5: Selo Fundador e um acessorio exclusivo (preco 0, flag exclusivo)."""

    def test_item_existe_e_e_exclusivo(self):
        it = catalog.item("selo_fundador")
        self.assertIsNotNone(it)
        self.assertEqual(it["preco"], 0)
        self.assertTrue(it["exclusivo"])
        self.assertEqual(it["tipo"], "acessorio")

    def test_nao_pode_ser_comprado(self):
        ok, motivo = catalog.pode_comprar("selo_fundador", saldo=999, possui=set(), floresceu=True)
        self.assertFalse(ok)
        self.assertIn("exclusivo", motivo.lower())

    def test_so_fundador_equipa(self):
        ok, _ = catalog.pode_equipar("selo_fundador", "acessorio", possui=set(), fundador=True)
        self.assertTrue(ok)
        ok, motivo = catalog.pode_equipar("selo_fundador", "acessorio", possui=set(), fundador=False)
        self.assertFalse(ok)

    def test_visual_mantem_selo_so_para_fundador(self):
        equip = {"acessorio": "selo_fundador"}
        v_fund = catalog.montar_visual(set(), equip, fundador=True)
        self.assertEqual(v_fund["acessorio"], "selo_fundador")
        v_nao = catalog.montar_visual(set(), equip, fundador=False)
        self.assertIsNone(v_nao["acessorio"])


if __name__ == "__main__":
    unittest.main()
