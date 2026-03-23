#include <stdio.h>
void main(){
	int choice;
	
	do{printf("가위는 1, 바위는 2, 보자기는 3 종료는 0을 입력하시오:");
	scanf("%d",&choice);
		switch(choice){
			case 1: printf("가위를 냈습니다!\n");
			break;
			case 2: printf("바위를 냈습니다!\n");
			break;
			case 3: printf("보를 냈습니다!\n");
			break;
			case 0: printf("당신이 0을 입력하여 가위, 바위, 보를 종료합니다.");
			break;
			default: printf("당신은 가위, 바위, 보를 선택하지 않았습니다.\n");
	}
	}while(choice!=0);
	
}
